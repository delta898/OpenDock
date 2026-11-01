#!/usr/bin/env python3
import importlib.util
import getpass
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from opendock_groups import group_services, validate_services
import opendock_settings as SETTINGS


ROOT_DIR = Path(__file__).resolve().parents[1]
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
    "mail": [
        Field("SMTP_HOST", "required-user"),
        Field("SMTP_PORT", "defaulted-choice", default="587"),
        Field("SMTP_USERNAME", "required-user"),
        Field("SMTP_PASSWORD", "secret-user"),
        Field("SMTP_FROM_ADDRESS", "required-user"),
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
                "Used only during first installation. Changing this setting later "
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
    "mattermost": [
        Field("MATTERMOST_SUBDOMAIN", "defaulted-choice", default="chat"),
        Field("MATTERMOST_DB_PASSWORD", "generated-secret"),
    ],
    "supabase": [
        Field("SUPABASE_SUBDOMAIN", "defaulted-choice", default="supabase"),
        Field("SUPABASE_DB_PASSWORD", "generated-secret"),
        Field("SUPABASE_JWT_SECRET", "generated-secret"),
        Field("SUPABASE_ANON_KEY", "generated-secret"),
        Field("SUPABASE_SERVICE_ROLE_KEY", "generated-secret"),
        Field("SUPABASE_PUBLISHABLE_KEY", "generated-secret"),
        Field("SUPABASE_SECRET_KEY", "generated-secret"),
        Field("SUPABASE_ANON_KEY_ASYMMETRIC", "generated-secret"),
        Field("SUPABASE_SERVICE_ROLE_KEY_ASYMMETRIC", "generated-secret"),
        Field("SUPABASE_JWT_KEYS", "generated-secret"),
        Field("SUPABASE_JWT_JWKS", "generated-secret"),
        Field("SUPABASE_SECRET_KEY_BASE", "generated-secret"),
        Field("SUPABASE_PG_META_CRYPTO_KEY", "generated-secret"),
        Field("SUPABASE_DASHBOARD_USER", "defaulted-choice", default="opendock"),
        Field(
            "SUPABASE_DASHBOARD_PASSWORD",
            "initial-credential",
            note="Used for HTTP Basic Auth login to Supabase Studio dashboard.",
        ),
        Field("SUPABASE_STUDIO_DEFAULT_ORGANIZATION", "defaulted-choice", default="OpenDock"),
        Field("SUPABASE_STUDIO_DEFAULT_PROJECT", "defaulted-choice", default="OpenDock"),
    ],
    "hermes": [
        Field("HERMES_SUBDOMAIN", "defaulted-choice", default="hermes"),
        Field("HERMES_DASHBOARD_USERNAME", "defaulted-choice", default="opendock"),
        Field(
            "HERMES_DASHBOARD_PASSWORD",
            "secret-user",
            note=(
                "Used at runtime for Hermes dashboard login. Enter a password; "
                "OpenDock stores it privately and does not display it."
            ),
        ),
        Field("HERMES_DASHBOARD_SECRET", "generated-secret"),
    ],
}

MARIADB_DEPENDENCIES = {
    "wordpress",
    "nextcloud",
}
POSTGRES_DEPENDENCIES = {
    "mastodon",
    "mattermost",
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
    elif target == "mail":
        services = []
    elif (ROOT_DIR / "services" / target / "compose.yml").is_file():
        services = [target]
    else:
        group = group_services(target)
        if not group:
            raise SystemExit(f"Unknown target or missing compose.yml: {target}")
        validate_services(group)
        services = group

    sections = [] if target == "mail" else ["global"]
    if target in ("infra", "all") or any(s in MARIADB_DEPENDENCIES for s in services):
        sections.append("mariadb")
    if target in ("infra", "all") or any(s in POSTGRES_DEPENDENCIES for s in services):
        sections.append("postgres")
    if target == "mail":
        sections.append("mail")

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


def prompt_secret(field, values):
    if is_real_value(field.name, values):
        print(f"{field.name} [keep existing]")
        answer = input("  Enter a new value? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            return None

    while True:
        value = getpass.getpass(f"{field.name}: ").strip()
        if value:
            return value
        print("  Required. Please enter a value.")


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


def update_settings(updates):
    changed = SETTINGS.write_values(updates)
    return changed, [], SETTINGS.BACKUPS_CREATED[:]


def print_summary(changed, generated_keys, backup):
    print()
    if changed:
        print("Updated OpenDock configuration:")
        for key in sorted(changed):
            if key in generated_keys:
                print(f"  {key} generated")
            else:
                print(f"  {key}")
    else:
        print("Nothing changed.")

    if backup:
        print()
        for path in backup:
            print(f"Backup: {path.relative_to(ROOT_DIR)}")

    if generated_keys:
        print()
        print("Generated values were not printed; see the corresponding owner-specific .env file.")


def print_credential_notices(changed):
    if "HERMES_DASHBOARD_PASSWORD" in changed:
        print()
        print("Hermes dashboard password is stored in private services/hermes/.env.")
        print("Run './opendock launch hermes' to apply a changed password.")
    if "NEXTCLOUD_ADMIN_PASSWORD" in changed:
        print()
        print("Nextcloud initial admin password is stored in services/nextcloud/.env.")
        print("Changing it later will not reset an installed Nextcloud password.")
    if "MASTODON_ADMIN_PASSWORD" in changed:
        print()
        print("Mastodon owner password is stored in services/mastodon/.env.")
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

    SETTINGS.initialize()
    values = SETTINGS.load_values(process_env=False)

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
        elif field.kind == "secret-user":
            result = prompt_secret(field, values)
            if result is not None:
                chosen[field.name] = result

    generate_keys = values_to_generate(fields, values, chosen)
    generated = SECRETS.generate_values(generate_keys, values)
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

    changed, _kept, backup = update_settings(updates)

    print_summary(changed, set(generated), backup)
    print_credential_notices(changed)
    print()
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
