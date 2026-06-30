#!/usr/bin/env python3
import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


ROOT_DIR = Path(__file__).resolve().parents[1]
COMMON_ENV = ROOT_DIR / "common.env"
COMMON_ENV_EXAMPLE = ROOT_DIR / "common.env.example"
SECRETS_SCRIPT = ROOT_DIR / "scripts" / "opendock-secrets.py"


@dataclass(frozen=True)
class Field:
    name: str
    kind: str
    default: Optional[str] = None
    note: Optional[str] = None


def load_secrets_module():
    spec = importlib.util.spec_from_file_location("opendock_secrets", SECRETS_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SECRETS = load_secrets_module()


CONFIG_FIELDS = {
    "global": [
        Field("STACK_DOMAIN", "required-user"),
    ],
    "mariadb": [
        Field("MARIADB_ROOT_PASSWORD", "generated-secret"),
    ],
    "postgres": [
        Field("POSTGRES_ADMIN_USER", "defaulted-choice", default="opendock"),
        Field("POSTGRES_ADMIN_PASSWORD", "generated-secret"),
    ],
    "homepage": [
        Field("HOMEPAGE_SUBDOMAIN", "defaulted-choice", default="home"),
    ],
    "wordpress": [
        Field("WORDPRESS_SUBDOMAIN", "defaulted-choice", default="blog"),
        Field("WORDPRESS_DB_PASSWORD", "generated-secret"),
    ],
    "nextcloud": [
        Field("NEXTCLOUD_SUBDOMAIN", "defaulted-choice", default="cloud"),
        Field("NEXTCLOUD_DB_PASSWORD", "generated-secret"),
        Field(
            "NEXTCLOUD_ADMIN_PASSWORD",
            "initial-credential",
            note=(
                "Used only during first installation. Changing common.env later "
                "does not reset an installed Nextcloud account."
            ),
        ),
    ],
    "immich": [
        Field("IMMICH_SUBDOMAIN", "defaulted-choice", default="photos"),
        Field("IMMICH_DB_PASSWORD", "generated-secret"),
    ],
    "jellyfin": [
        Field("JELLYFIN_SUBDOMAIN", "defaulted-choice", default="media"),
    ],
    "n8n": [
        Field("N8N_SUBDOMAIN", "defaulted-choice", default="n8n"),
    ],
    "uptime-kuma": [
        Field("UPTIME_KUMA_SUBDOMAIN", "defaulted-choice", default="uptime"),
    ],
    "mastodon": [
        Field("MASTODON_SUBDOMAIN", "defaulted-choice", default="social"),
        Field("MASTODON_ADMIN_USERNAME", "defaulted-choice", default="opendock"),
        Field("MASTODON_ADMIN_EMAIL", "required-user"),
        Field(
            "MASTODON_ADMIN_PASSWORD",
            "initial-credential",
            note=(
                "Used only when OpenDock creates the first Mastodon owner account."
            ),
        ),
        Field("MASTODON_DB_PASSWORD", "generated-secret"),
        Field("MASTODON_SECRET_KEY_BASE", "generated-secret"),
        Field("MASTODON_OTP_SECRET", "generated-secret"),
        Field("MASTODON_ACTIVE_RECORD_ENCRYPTION_DETERMINISTIC_KEY", "generated-secret"),
        Field("MASTODON_ACTIVE_RECORD_ENCRYPTION_KEY_DERIVATION_SALT", "generated-secret"),
        Field("MASTODON_ACTIVE_RECORD_ENCRYPTION_PRIMARY_KEY", "generated-secret"),
        Field("MASTODON_VAPID_PRIVATE_KEY", "generated-secret"),
        Field("MASTODON_VAPID_PUBLIC_KEY", "generated-secret"),
    ],
}

MARIADB_DEPENDENCIES = {
    "wordpress",
    "nextcloud",
}
POSTGRES_DEPENDENCIES = {
    "mastodon",
}


def service_targets():
    services_dir = ROOT_DIR / "services"
    if not services_dir.is_dir():
        return []
    return sorted(compose.parent.name for compose in services_dir.glob("*/compose.yml"))


def resolve_sections(target):
    if target == "all":
        services = service_targets()
    elif target == "services":
        services = service_targets()
    elif target in ("infra", "gateway"):
        services = []
    elif (ROOT_DIR / "services" / target / "compose.yml").is_file():
        services = [target]
    else:
        raise SystemExit(f"Unknown target or missing compose.yml: {target}")

    sections = ["global"]
    if target in ("infra", "all") or any(s in MARIADB_DEPENDENCIES for s in services):
        sections.append("mariadb")
    if target in ("infra", "all") or any(s in POSTGRES_DEPENDENCIES for s in services):
        sections.append("postgres")

    for service in services:
        if service in CONFIG_FIELDS:
            sections.append(service)

    return sections


def selected_fields(sections):
    fields = []
    seen = set()
    for section in sections:
        for field in CONFIG_FIELDS.get(section, []):
            if field.name in seen:
                continue
            fields.append(field)
            seen.add(field.name)
    return fields


def is_real_value(name, values):
    value = values.get(name, "")
    if not value:
        return False
    if name == "STACK_DOMAIN" and value == "example.com":
        return False
    if name == "MASTODON_ADMIN_USERNAME" and value.lower() == "admin":
        return False
    return not SECRETS.is_placeholder(value)


def prompt_required(field, values):
    current = values.get(field.name, "")
    if is_real_value(field.name, values):
        answer = input(f"{field.name} [{current}]: ").strip()
        return current if not answer else answer

    while True:
        answer = input(f"{field.name}: ").strip()
        if answer:
            return answer
        print("  Required. Please enter a value.")


def prompt_defaulted(field, values):
    current = values.get(field.name, "")
    default = current if is_real_value(field.name, values) else field.default
    if default:
        answer = input(f"{field.name} [{default}]: ").strip()
        return default if not answer else answer

    answer = input(f"{field.name}: ").strip()
    return answer


def prompt_initial_credential(field, values):
    if is_real_value(field.name, values):
        print(f"{field.name} [keep existing]")
        if field.note:
            print(f"  {field.note}")
        answer = input("  Enter a new value? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            return None
        value = input(f"  New {field.name} [auto-generate]: ").strip()
        return value or "__GENERATE__"

    if field.note:
        print(f"{field.name}")
        print(f"  {field.note}")
    value = input(f"{field.name} [auto-generate]: ").strip()
    return value or "__GENERATE__"


def values_to_generate(fields, values, chosen):
    keys = set()
    for field in fields:
        if field.kind == "generated-secret" and not is_real_value(field.name, values):
            keys.add(field.name)
        if field.kind == "initial-credential" and chosen.get(field.name) == "__GENERATE__":
            keys.add(field.name)

    if keys & SECRETS.VAPID_KEYS:
        keys.update(SECRETS.VAPID_KEYS)

    return keys


def update_common_env(updates, selected_keys, should_backup):
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
        if key in updates and current != updates[key]:
            updated_lines.append(f"{key}={updates[key]}")
            changed.append(key)
        else:
            updated_lines.append(line)
            kept.append(key)

    missing = sorted(selected_keys - seen)
    if missing:
        if updated_lines and updated_lines[-1].strip():
            updated_lines.append("")
        updated_lines.append("# OpenDock setup values.")
        for key in missing:
            if key in updates:
                updated_lines.append(f"{key}={updates[key]}")
                changed.append(key)

    if changed and should_backup:
        backup = SECRETS.backup_common_env()
    else:
        backup = None

    COMMON_ENV.write_text("\n".join(updated_lines) + "\n")
    COMMON_ENV.chmod(0o600)
    return changed, kept, backup


def print_summary(changed, generated_keys, backup):
    print()
    if changed:
        print("Updated common.env:")
        for key in sorted(changed):
            if key in generated_keys:
                print(f"  {key} generated")
            else:
                print(f"  {key}")
    else:
        print("Nothing changed.")

    if backup:
        print()
        print(f"Backup: {backup.relative_to(ROOT_DIR)}")

    if generated_keys:
        print()
        print("Generated values were not printed; see common.env when needed.")


def print_credential_notices(changed):
    if "NEXTCLOUD_ADMIN_PASSWORD" in changed:
        print()
        print("Nextcloud initial admin password is stored in common.env.")
        print("Changing common.env later will not reset an installed Nextcloud password.")
    if "MASTODON_ADMIN_PASSWORD" in changed:
        print()
        print("Mastodon owner password is stored in common.env.")
        print("It is used only when OpenDock creates the first Mastodon owner account.")


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "all"
    sections = resolve_sections(target)
    fields = selected_fields(sections)

    print(f"OpenDock setup: {target}")
    print()
    print("Existing values are kept when you press Enter.")
    print("Secrets are generated or kept without printing their values.")
    print()

    created = SECRETS.ensure_common_env()
    values = SECRETS.parse_env(COMMON_ENV)

    chosen = {}
    for field in fields:
        if field.kind == "required-user":
            chosen[field.name] = prompt_required(field, values)
        elif field.kind == "defaulted-choice":
            chosen[field.name] = prompt_defaulted(field, values)
        elif field.kind == "initial-credential":
            result = prompt_initial_credential(field, values)
            if result is not None:
                chosen[field.name] = result

    generate_keys = values_to_generate(fields, values, chosen)
    generated = SECRETS.generate_values(generate_keys)
    for field in fields:
        if (
            field.kind == "initial-credential"
            and chosen.get(field.name) == "__GENERATE__"
            and field.name not in generated
        ):
            generated[field.name] = SECRETS.generated_initial_credential()

    updates = {}
    updates.update({k: v for k, v in chosen.items() if v != "__GENERATE__"})
    updates.update(generated)

    selected_keys = {field.name for field in fields}
    changed, _kept, backup = update_common_env(
        updates, selected_keys, should_backup=not created
    )

    print_summary(changed, set(generated), backup)
    print_credential_notices(changed)
    print()
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
