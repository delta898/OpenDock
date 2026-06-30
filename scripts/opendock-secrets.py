#!/usr/bin/env python3
import os
import secrets
import shutil
import string
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
COMMON_ENV = ROOT_DIR / "common.env"
COMMON_ENV_EXAMPLE = ROOT_DIR / "common.env.example"
MASTODON_ENV = ROOT_DIR / "services" / "mastodon" / ".env"
BACKUP_DIR = ROOT_DIR / "backups" / "common-env"

MASTODON_KEYS = {
    "MASTODON_DB_PASSWORD",
    "MASTODON_ACTIVE_RECORD_ENCRYPTION_DETERMINISTIC_KEY",
    "MASTODON_ACTIVE_RECORD_ENCRYPTION_KEY_DERIVATION_SALT",
    "MASTODON_ACTIVE_RECORD_ENCRYPTION_PRIMARY_KEY",
    "MASTODON_SECRET_KEY_BASE",
    "MASTODON_OTP_SECRET",
    "MASTODON_VAPID_PRIVATE_KEY",
    "MASTODON_VAPID_PUBLIC_KEY",
}
INFRA_KEYS = {"MARIADB_ROOT_PASSWORD", "POSTGRES_ADMIN_USER", "POSTGRES_ADMIN_PASSWORD"}
SERVICE_KEYS = {
    "infra": INFRA_KEYS,
    "wordpress": {"MARIADB_ROOT_PASSWORD", "WORDPRESS_DB_PASSWORD"},
    "nextcloud": {
        "MARIADB_ROOT_PASSWORD",
        "NEXTCLOUD_DB_PASSWORD",
        "NEXTCLOUD_ADMIN_PASSWORD",
    },
    "immich": {"IMMICH_DB_PASSWORD"},
    "mastodon": {"POSTGRES_ADMIN_USER", "POSTGRES_ADMIN_PASSWORD"} | MASTODON_KEYS,
}
GENERATED_KEYS = set().union(INFRA_KEYS, *SERVICE_KEYS.values())
VAPID_KEYS = {"MASTODON_VAPID_PRIVATE_KEY", "MASTODON_VAPID_PUBLIC_KEY"}


def parse_env(path):
    values = {}
    if not path.exists():
        return values

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")

    return values


def is_placeholder(value):
    normalized = value.strip().lower()
    return (
        not normalized
        or normalized.startswith("change")
        or normalized.startswith("changeme")
        or normalized == "password"
    )


def service_targets():
    services_dir = ROOT_DIR / "services"
    if not services_dir.is_dir():
        return []
    return sorted(compose.parent.name for compose in services_dir.glob("*/compose.yml"))


def target_keys(target):
    if target == "all":
        return set(GENERATED_KEYS)
    if target == "services":
        keys = set()
        for service in service_targets():
            keys.update(SERVICE_KEYS.get(service, set()))
        return keys
    return set(SERVICE_KEYS.get(target, set()))


def mastodon_image():
    version = parse_env(MASTODON_ENV).get("MASTODON_VERSION", "v4.4.3")
    return f"ghcr.io/mastodon/mastodon:{version}"


def docker_capture(image, *command):
    try:
        result = subprocess.run(
            ["docker", "run", "--rm", image, *command],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError as error:
        raise SystemExit("Docker is required to generate Mastodon secrets.") from error
    except subprocess.CalledProcessError as error:
        output = "\n".join(
            part.strip() for part in (error.stdout, error.stderr) if part.strip()
        )
        raise SystemExit(f"Could not generate Mastodon secrets with Docker.\n{output}") from error

    return result.stdout.strip()


def generated_password(length=36):
    return secrets.token_urlsafe(length)


def generated_initial_credential(length=20):
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generated_alnum(length=48):
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def keys_needing_update(values, selected_keys):
    needed = {key for key in selected_keys if is_placeholder(values.get(key, ""))}
    if needed & VAPID_KEYS:
        needed.update(VAPID_KEYS)
    return needed


def generate_values(needed):
    generated = {}
    if not needed:
        return generated

    if "MARIADB_ROOT_PASSWORD" in needed:
        generated["MARIADB_ROOT_PASSWORD"] = generated_password()
    if "POSTGRES_ADMIN_USER" in needed:
        generated["POSTGRES_ADMIN_USER"] = "opendock"
    if "POSTGRES_ADMIN_PASSWORD" in needed:
        generated["POSTGRES_ADMIN_PASSWORD"] = generated_password()
    if "WORDPRESS_DB_PASSWORD" in needed:
        generated["WORDPRESS_DB_PASSWORD"] = generated_password()
    if "NEXTCLOUD_DB_PASSWORD" in needed:
        generated["NEXTCLOUD_DB_PASSWORD"] = generated_password()
    if "NEXTCLOUD_ADMIN_PASSWORD" in needed:
        generated["NEXTCLOUD_ADMIN_PASSWORD"] = generated_initial_credential()
    if "IMMICH_DB_PASSWORD" in needed:
        generated["IMMICH_DB_PASSWORD"] = generated_alnum()
    if "MASTODON_DB_PASSWORD" in needed:
        generated["MASTODON_DB_PASSWORD"] = generated_password()
    if "MASTODON_ACTIVE_RECORD_ENCRYPTION_DETERMINISTIC_KEY" in needed:
        generated["MASTODON_ACTIVE_RECORD_ENCRYPTION_DETERMINISTIC_KEY"] = (
            secrets.token_hex(32)
        )
    if "MASTODON_ACTIVE_RECORD_ENCRYPTION_KEY_DERIVATION_SALT" in needed:
        generated["MASTODON_ACTIVE_RECORD_ENCRYPTION_KEY_DERIVATION_SALT"] = (
            secrets.token_hex(32)
        )
    if "MASTODON_ACTIVE_RECORD_ENCRYPTION_PRIMARY_KEY" in needed:
        generated["MASTODON_ACTIVE_RECORD_ENCRYPTION_PRIMARY_KEY"] = secrets.token_hex(32)

    needs_mastodon_image = bool(
        needed
        & {
            "MASTODON_SECRET_KEY_BASE",
            "MASTODON_OTP_SECRET",
            "MASTODON_VAPID_PRIVATE_KEY",
            "MASTODON_VAPID_PUBLIC_KEY",
        }
    )
    image = mastodon_image() if needs_mastodon_image else None
    if image:
        print(f"Generating Mastodon secrets with {image}")

    if "MASTODON_SECRET_KEY_BASE" in needed:
        generated["MASTODON_SECRET_KEY_BASE"] = docker_capture(
            image, "bundle", "exec", "rails", "secret"
        )
    if "MASTODON_OTP_SECRET" in needed:
        generated["MASTODON_OTP_SECRET"] = docker_capture(
            image, "bundle", "exec", "rails", "secret"
        )
    if needed & VAPID_KEYS:
        vapid = docker_capture(
            image,
            "bundle",
            "exec",
            "rails",
            "mastodon:webpush:generate_vapid_key",
        )
        vapid_values = {}
        for line in vapid.splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            vapid_values[key.strip()] = value.strip()

        required_vapid = {"VAPID_PRIVATE_KEY", "VAPID_PUBLIC_KEY"}
        if not required_vapid.issubset(vapid_values):
            raise SystemExit("Mastodon VAPID generator did not return the expected keys.")

        generated["MASTODON_VAPID_PRIVATE_KEY"] = vapid_values["VAPID_PRIVATE_KEY"]
        generated["MASTODON_VAPID_PUBLIC_KEY"] = vapid_values["VAPID_PUBLIC_KEY"]

    return generated


def ensure_common_env():
    if COMMON_ENV.exists():
        COMMON_ENV.chmod(0o600)
        return False

    if not COMMON_ENV_EXAMPLE.exists():
        raise SystemExit("Missing common.env and common.env.example.")

    shutil.copyfile(COMMON_ENV_EXAMPLE, COMMON_ENV)
    COMMON_ENV.chmod(0o600)
    print("Created common.env from common.env.example")
    return True


def backup_common_env():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = BACKUP_DIR / f"common.env.{timestamp}.bak"
    shutil.copy2(COMMON_ENV, backup)
    backup.chmod(0o600)
    return backup


def update_common_env(generated, force_update, selected_keys, should_backup):
    lines = COMMON_ENV.read_text().splitlines()
    changed = []
    kept = []
    seen = set()
    updated_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            updated_lines.append(line)
            continue

        key, current = line.split("=", 1)
        key = key.strip()
        if key not in selected_keys:
            updated_lines.append(line)
            continue

        seen.add(key)
        if key in generated and (is_placeholder(current) or key in force_update):
            updated_lines.append(f"{key}={generated[key]}")
            changed.append(key)
        else:
            updated_lines.append(line)
            kept.append(key)

    missing = sorted(selected_keys - seen)
    if missing:
        if updated_lines and updated_lines[-1].strip():
            updated_lines.append("")
        updated_lines.append("# OpenDock generated secrets.")
        for key in missing:
            if key in generated:
                updated_lines.append(f"{key}={generated[key]}")
                changed.append(key)

    if changed and should_backup:
        backup = backup_common_env()
    else:
        backup = None

    COMMON_ENV.write_text("\n".join(updated_lines) + "\n")
    COMMON_ENV.chmod(0o600)
    return changed, kept, backup


def print_nextcloud_notice(changed):
    if "NEXTCLOUD_ADMIN_PASSWORD" not in changed:
        return

    print()
    print("Nextcloud initial admin password was generated in common.env.")
    print("Login user: NEXTCLOUD_ADMIN_USER")
    print("Login password: NEXTCLOUD_ADMIN_PASSWORD")
    print("Changing common.env later will not reset an installed Nextcloud password.")


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "all"
    quiet = os.environ.get("OPEN_DOCK_QUIET_SECRETS") == "1"
    selected_keys = target_keys(target)

    created = ensure_common_env()
    existing = parse_env(COMMON_ENV)
    needed = keys_needing_update(existing, selected_keys)
    force_update = VAPID_KEYS if needed & VAPID_KEYS else set()

    if not needed:
        if not quiet:
            print("Generated secrets already exist in common.env. Nothing changed.")
        return 0

    generated = generate_values(needed)
    changed, kept, backup = update_common_env(
        generated, force_update, selected_keys, should_backup=not created
    )

    print()
    if changed:
        print("Updated common.env:")
        for key in sorted(changed):
            print(f"  {key}")
    if kept and not quiet:
        print("Kept existing common.env values:")
        for key in sorted(kept):
            print(f"  {key}")
    if backup:
        print()
        print(f"Backup: {backup.relative_to(ROOT_DIR)}")

    print_nextcloud_notice(changed)

    print()
    print("Done. Generated values were not printed; see common.env when needed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
