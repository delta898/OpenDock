#!/usr/bin/env python3
import re
import sys
import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
COMMON_ENV = ROOT_DIR / "common.env"
COMMON_ENV_EXAMPLE = ROOT_DIR / "common.env.example"
TARGET = sys.argv[1] if len(sys.argv) > 1 else "all"
QUIET = os.environ.get("CHECK_CONFIG_QUIET") == "1"
ENV_KEY_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
INTERPOLATION_RE = re.compile(
    r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?:(:?[-?=+])([^}]*))?\}"
)
GLOBAL_REQUIRED = {"STACK_DOMAIN"}
SERVICE_REQUIRED = {
    "mastodon": {"MASTODON_ADMIN_EMAIL"},
}


def service_env_key(service):
    return f"{service.replace('-', '_').upper()}_SUBDOMAIN"


def parse_env_file(path):
    values = {}
    if not path.exists():
        return values

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if not ENV_KEY_RE.fullmatch(key):
            continue

        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]

        values[key] = value

    return values


def service_targets():
    services_dir = ROOT_DIR / "services"
    if not services_dir.is_dir():
        return []
    return sorted(compose.parent.name for compose in services_dir.glob("*/compose.yml"))


def target_dir(target):
    if target in ("infra", "gateway"):
        return ROOT_DIR / target
    return ROOT_DIR / "services" / target


def all_targets():
    targets = ["infra"]
    if (ROOT_DIR / "gateway" / "compose.yml").is_file():
        targets.append("gateway")
    targets.extend(service_targets())
    return targets


def resolve_targets(target):
    if target == "all":
        return all_targets()
    if target == "services":
        return service_targets()
    if target in ("infra", "gateway"):
        return [target]

    compose = ROOT_DIR / "services" / target / "compose.yml"
    if not compose.is_file():
        raise SystemExit(f"Unknown target or missing compose.yml: {target}")
    return [target]


def compose_variables(path):
    required = set()
    optional = {}

    text = path.read_text()
    for match in INTERPOLATION_RE.finditer(text):
        name, operator, value = match.groups()
        if not operator or operator in ("?", ":?"):
            required.add(name)
        elif operator in ("-", ":-", "=", ":="):
            optional.setdefault(name, value)

    return required, optional


def is_placeholder(name, value, example_values):
    if not value:
        return True

    if name == "STACK_DOMAIN" and value == "example.com":
        return True

    if re.search(r"(PASSWORD|SECRET|TOKEN|KEY)", name):
        normalized = value.strip().lower()
        if normalized.startswith("change") or normalized in {"changeme", "password"}:
            return True
        if example_values.get(name) == value:
            return True

    return False


def check_target(target, common_values, example_values):
    directory = target_dir(target)
    compose = directory / "compose.yml"
    if not compose.is_file():
        return {
            "target": target,
            "missing": [f"compose.yml for {target}"],
            "placeholders": [],
            "optional": {},
        }

    env = {}
    env.update(common_values)

    service_env = directory / ".env"
    if service_env.exists():
        env.update(parse_env_file(service_env))

    required, optional = compose_variables(compose)
    required.update(GLOBAL_REQUIRED)
    required.update(SERVICE_REQUIRED.get(target, set()))
    missing = sorted(name for name in required if not env.get(name))
    placeholders = sorted(
        name
        for name in required
        if name in env and is_placeholder(name, env.get(name, ""), example_values)
    )

    optional_missing = {}
    target_subdomain = service_env_key(target)
    for name, default in sorted(optional.items()):
        if name in env or name != target_subdomain:
            continue
        optional_missing[name] = default

    return {
        "target": target,
        "missing": missing,
        "placeholders": placeholders,
        "optional": optional_missing,
    }


def print_results(results):
    failed = False

    for result in results:
        target = result["target"]
        missing = result["missing"]
        placeholders = result["placeholders"]
        optional = result["optional"]
        should_print = not QUIET or missing or placeholders

        if should_print:
            print(f"==> check-config: {target}")

        if missing:
            failed = True
            print("Missing required values:")
            for name in missing:
                print(f"  {name}")

        if placeholders:
            failed = True
            print("Required values still look like examples:")
            for name in placeholders:
                print(f"  {name}")

        if optional and not QUIET:
            print("Optional values missing, defaults will be used:")
            for name, default in optional.items():
                print(f"  {name}={default}")

        if not missing and not placeholders and not optional and not QUIET:
            print("OK")

        if should_print:
            print()

    if failed:
        print("Set external values such as STACK_DOMAIN in common.env.")
        print(f"Run `make setup {TARGET}` to review and fill user-facing values.")
        print("Run `make secrets` to fill generated passwords and app secrets.")
        return 1

    return 0


def print_missing_common_env():
    print("Missing required file: common.env")
    print()
    print("To continue:")
    print("  make setup")
    print("  make check-config")
    print()
    print("Or configure manually:")
    print("  cp common.env.example common.env")
    print("  nano common.env  # set STACK_DOMAIN")
    print("  make secrets")


def main():
    if not COMMON_ENV.exists():
        print_missing_common_env()
        return 1

    common_values = parse_env_file(COMMON_ENV)
    example_values = parse_env_file(COMMON_ENV_EXAMPLE)
    targets = resolve_targets(TARGET)
    results = [check_target(target, common_values, example_values) for target in targets]
    return print_results(results)


if __name__ == "__main__":
    raise SystemExit(main())
