"""Supabase credential bundles and cross-field configuration validation."""

import base64
import hashlib
import hmac
import json
import re
import secrets
import shutil
import string
import subprocess
import sys
import time

from opendock_capabilities import (
    PreparationResult,
    ServiceContext,
    SecretGenerationContext,
    SecretPlan,
    SecretPlanningContext,
    ValidationContext,
    ValidationResult,
)


OPENDOCK_CAPABILITY_API_VERSION = 1
FUNCTIONS_ENV_NAME = "functions.env"
FUNCTIONS_ENV_EXAMPLE_NAME = "functions.env.example"


def post_launch(context: ServiceContext) -> None:
    """Run Supabase's post-launch readiness checks."""
    helper = context.service.directory / "opendock-post-launch.py"
    subprocess.run(
        [sys.executable, str(helper)],
        cwd=context.service.directory.parents[1],
        check=True,
    )


def prepare(context: ServiceContext) -> PreparationResult:
    """Create the private Edge Functions env file when it is first needed."""
    target = context.service.directory / FUNCTIONS_ENV_NAME
    example = context.service.directory / FUNCTIONS_ENV_EXAMPLE_NAME
    if target.is_file():
        target.chmod(0o600)
        return PreparationResult("not_needed")
    if not example.is_file():
        raise RuntimeError(
            f"Missing {example.relative_to(context.service.directory.parent.parent)}; "
            "cannot prepare Supabase Edge Functions configuration."
        )
    shutil.copyfile(example, target)
    target.chmod(0o600)
    return PreparationResult("completed", "created private services/supabase/functions.env")

SUPABASE_JWT_KEYS = {
    "SUPABASE_JWT_SECRET",
    "SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
}
SUPABASE_NEW_AUTH_KEYS = {
    "SUPABASE_PUBLISHABLE_KEY",
    "SUPABASE_SECRET_KEY",
    "SUPABASE_ANON_KEY_ASYMMETRIC",
    "SUPABASE_SERVICE_ROLE_KEY_ASYMMETRIC",
    "SUPABASE_JWT_KEYS",
    "SUPABASE_JWT_JWKS",
}


def _placeholder(name: str, value: str, examples) -> bool:
    normalized = value.strip().lower()
    if not value or normalized.startswith(("change", "changeme")) or normalized == "password":
        return True
    return examples.get(name) == value


def plan_secrets(context: SecretPlanningContext) -> SecretPlan:
    """Keep legacy JWTs and modern signing keys consistent as one bundle."""
    missing = {
        key for key in context.selected_keys
        if key in SUPABASE_JWT_KEYS | SUPABASE_NEW_AUTH_KEYS
        and _placeholder(key, context.settings.get(key, ""), {})
    }
    if missing & SUPABASE_JWT_KEYS:
        missing.update(SUPABASE_JWT_KEYS)
        missing.update(SUPABASE_NEW_AUTH_KEYS)
    elif missing & SUPABASE_NEW_AUTH_KEYS:
        missing.update(SUPABASE_NEW_AUTH_KEYS)
    return SecretPlan(frozenset(missing))


def _generated_alnum(length: int) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _jwt(secret: str, role: str, exp_years: int = 10) -> str:
    now = time.time()
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "role": role,
        "iss": "supabase",
        "iat": int(now),
        "exp": int(now + exp_years * 365 * 24 * 3600),
    }
    encode = lambda value: base64.urlsafe_b64encode(
        json.dumps(value, separators=(",", ":")).encode("utf-8")
    ).decode("utf-8").rstrip("=")
    message = f"{encode(header)}.{encode(payload)}"
    signature = hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).digest()
    return f"{message}.{base64.urlsafe_b64encode(signature).decode('utf-8').rstrip('=')}"


def _new_auth(jwt_secret: str, run_image) -> dict[str, str]:
    script = r"""
const crypto = require("crypto");
const fs = require("fs");
const jwtSecret = fs.readFileSync(0, "utf8");
const { privateKey } = crypto.generateKeyPairSync("ec", { namedCurve: "P-256" });
const jwkPrivate = privateKey.export({ format: "jwk" });
const kid = crypto.randomUUID();
const octKey = { kty: "oct", k: Buffer.from(jwtSecret).toString("base64url"), alg: "HS256" };
const privateEc = {
  kty: "EC", kid, use: "sig", key_ops: ["sign", "verify"], alg: "ES256",
  ext: true, crv: jwkPrivate.crv, x: jwkPrivate.x, y: jwkPrivate.y, d: jwkPrivate.d,
};
const publicEc = {
  kty: "EC", kid, use: "sig", key_ops: ["verify"], alg: "ES256",
  ext: true, crv: jwkPrivate.crv, x: jwkPrivate.x, y: jwkPrivate.y,
};
function signES256(payload) {
  const header = { alg: "ES256", typ: "JWT", kid };
  const encodedHeader = Buffer.from(JSON.stringify(header)).toString("base64url");
  const encodedPayload = Buffer.from(JSON.stringify(payload)).toString("base64url");
  const data = `${encodedHeader}.${encodedPayload}`;
  const signature = crypto.sign("SHA256", Buffer.from(data), {
    key: privateKey, dsaEncoding: "ieee-p1363",
  }).toString("base64url");
  return `${data}.${signature}`;
}
function opaqueKey(prefix) {
  const random = crypto.randomBytes(17).toString("base64url").slice(0, 22);
  const intermediate = prefix + random;
  const checksum = crypto.createHash("sha256")
    .update(`supabase-self-hosted|${intermediate}`).digest("base64url").slice(0, 8);
  return `${intermediate}_${checksum}`;
}
const iat = Math.floor(Date.now() / 1000);
const exp = iat + 5 * 365 * 24 * 3600;
process.stdout.write(JSON.stringify({
  SUPABASE_PUBLISHABLE_KEY: opaqueKey("sb_publishable_"),
  SUPABASE_SECRET_KEY: opaqueKey("sb_secret_"),
  SUPABASE_ANON_KEY_ASYMMETRIC: signES256({ role: "anon", iss: "supabase", iat, exp }),
  SUPABASE_SERVICE_ROLE_KEY_ASYMMETRIC: signES256({ role: "service_role", iss: "supabase", iat, exp }),
  SUPABASE_JWT_KEYS: JSON.stringify([privateEc, octKey]),
  SUPABASE_JWT_JWKS: JSON.stringify({ keys: [publicEc, octKey] }),
}));
"""
    output = run_image("node:22-alpine", "node", "-e", script, input_text=jwt_secret)
    result = json.loads(output)
    if set(result) != SUPABASE_NEW_AUTH_KEYS:
        raise RuntimeError("Supabase key generator returned an unexpected key set.")
    return result


def generate_secrets(context: SecretGenerationContext) -> dict[str, str]:
    requested = context.requested_keys
    generated = {}
    jwt_secret = context.settings.get("SUPABASE_JWT_SECRET", "")
    if requested & SUPABASE_JWT_KEYS:
        jwt_secret = _generated_alnum(40)
        generated["SUPABASE_JWT_SECRET"] = jwt_secret
        generated["SUPABASE_ANON_KEY"] = _jwt(jwt_secret, "anon")
        generated["SUPABASE_SERVICE_ROLE_KEY"] = _jwt(jwt_secret, "service_role")
    if requested & SUPABASE_NEW_AUTH_KEYS:
        if _placeholder("SUPABASE_JWT_SECRET", jwt_secret, {}):
            raise RuntimeError("SUPABASE_JWT_SECRET must be generated before the new API keys.")
        context.report("generating Supabase publishable keys and ES256 signing keys")
        generated.update(_new_auth(jwt_secret, context.run_image))
    return {key: value for key, value in generated.items() if key in requested}


def _decode_jwt_parts(token: str):
    try:
        header, payload, _signature = token.split(".")
        decode = lambda part: json.loads(
            base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))
        )
        return decode(header), decode(payload)
    except (ValueError, TypeError, json.JSONDecodeError):
        return None, None


def _valid_hs256_jwt(token: str, secret: str, role: str) -> bool:
    try:
        header, payload, signature = token.split(".")
        message = f"{header}.{payload}".encode("utf-8")
        expected = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).digest()
        actual = base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (ValueError, TypeError, json.JSONDecodeError):
        return False
    return hmac.compare_digest(actual, expected) and claims.get("role") == role


def _validate_new_auth(values) -> list[str]:
    invalid = []
    patterns = {
        "SUPABASE_PUBLISHABLE_KEY": r"sb_publishable_[A-Za-z0-9_-]{22}_[A-Za-z0-9_-]{8}",
        "SUPABASE_SECRET_KEY": r"sb_secret_[A-Za-z0-9_-]{22}_[A-Za-z0-9_-]{8}",
    }
    for name, pattern in patterns.items():
        if values.get(name) and not re.fullmatch(pattern, values[name]):
            invalid.append(f"{name} (invalid opaque API key format)")

    try:
        signing_keys = json.loads(values.get("SUPABASE_JWT_KEYS", ""))
        public_jwks = json.loads(values.get("SUPABASE_JWT_JWKS", ""))
        public_keys = public_jwks.get("keys", [])
        private_ec = next(
            key for key in signing_keys
            if key.get("kty") == "EC" and key.get("alg") == "ES256" and key.get("d")
        )
        public_ec = next(
            key for key in public_keys
            if key.get("kty") == "EC" and key.get("alg") == "ES256"
        )
        signing_oct = next(key for key in signing_keys if key.get("kty") == "oct")
        public_oct = next(key for key in public_keys if key.get("kty") == "oct")
        expected_oct = base64.urlsafe_b64encode(
            values.get("SUPABASE_JWT_SECRET", "").encode("utf-8")
        ).decode("utf-8").rstrip("=")
        if private_ec.get("kid") != public_ec.get("kid") or public_ec.get("d"):
            raise ValueError("invalid EC key relationship")
        if signing_oct.get("k") != expected_oct or public_oct.get("k") != expected_oct:
            raise ValueError("symmetric key does not match JWT secret")
    except (json.JSONDecodeError, TypeError, AttributeError, StopIteration, ValueError):
        invalid.append("SUPABASE_JWT_KEYS/SUPABASE_JWT_JWKS (invalid or inconsistent JWKS)")
        return invalid

    for name, role in (
        ("SUPABASE_ANON_KEY_ASYMMETRIC", "anon"),
        ("SUPABASE_SERVICE_ROLE_KEY_ASYMMETRIC", "service_role"),
    ):
        header, payload = _decode_jwt_parts(values.get(name, ""))
        if (
            not header or not payload or header.get("alg") != "ES256"
            or header.get("kid") != public_ec.get("kid") or payload.get("role") != role
        ):
            invalid.append(f"{name} (does not match ES256 JWKS/{role})")
    return invalid


def validate_config(context: ValidationContext) -> ValidationResult:
    values = context.settings
    examples = context.examples
    invalid = []
    for name, minimum in (
        ("SUPABASE_JWT_SECRET", 32),
        ("SUPABASE_SECRET_KEY_BASE", 64),
        ("SUPABASE_PG_META_CRYPTO_KEY", 32),
    ):
        value = values.get(name, "")
        if value and not _placeholder(name, value, examples) and len(value) < minimum:
            invalid.append(f"{name} (must be at least {minimum} characters)")

    secret = values.get("SUPABASE_JWT_SECRET", "")
    if secret and not _placeholder("SUPABASE_JWT_SECRET", secret, examples):
        for name, role in (
            ("SUPABASE_ANON_KEY", "anon"),
            ("SUPABASE_SERVICE_ROLE_KEY", "service_role"),
        ):
            token = values.get(name, "")
            if token and not _placeholder(name, token, examples) and not _valid_hs256_jwt(token, secret, role):
                invalid.append(f"{name} (does not match SUPABASE_JWT_SECRET/{role})")

    auth_fields = {
        "SUPABASE_PUBLISHABLE_KEY", "SUPABASE_SECRET_KEY",
        "SUPABASE_ANON_KEY_ASYMMETRIC", "SUPABASE_SERVICE_ROLE_KEY_ASYMMETRIC",
        "SUPABASE_JWT_KEYS", "SUPABASE_JWT_JWKS",
    }
    if all(
        values.get(name) and not _placeholder(name, values[name], examples)
        for name in auth_fields
    ):
        invalid.extend(_validate_new_auth(values))
    return ValidationResult(tuple(invalid))
