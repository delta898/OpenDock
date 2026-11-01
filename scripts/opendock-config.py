#!/usr/bin/env python3
import importlib.util
import getpass
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from opendock_groups import group_services, validate_services
from opendock_catalog import ServiceCatalog, service_names
import opendock_settings as SETTINGS


ROOT_DIR = Path(__file__).resolve().parents[1]
SECRETS_SCRIPT = ROOT_DIR / "scripts" / "opendock-secrets.py"


@dataclass(frozen=True)
class Field:
    name: str
    kind: str
    default: Optional[str] = None
    note: Optional[str] = None
    change_notice: Optional[str] = None
    generated_notice: Optional[str] = None
    generator: Optional[str] = None
    length: Optional[int] = None
    required: Optional[bool] = None


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
    "mail": [
        Field("SMTP_HOST", "required-user"),
        Field("SMTP_PORT", "defaulted-choice", default="587"),
        Field("SMTP_USERNAME", "required-user"),
        Field("SMTP_PASSWORD", "secret-user"),
        Field("SMTP_FROM_ADDRESS", "required-user"),
    ],
}


def service_targets():
    return list(service_names(ROOT_DIR))


def resolve_sections(target):
    catalog = ServiceCatalog(ROOT_DIR)
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
    infra = catalog.platform.get("infra")
    shared_setup = {
        dependency
        for service in services
        for dependency in catalog.get(service).setup_dependencies
    }
    if target in ("infra", "all"):
        shared_setup.update(infra.shared_groups)
    if shared_setup:
        sections.extend(f"infra:{group}" for group in sorted(shared_setup))
    if target == "mail":
        sections.append("mail")

    for service in services:
        sections.append(service)

    return sections


def selected_fields(sections):
    fields = []
    seen = set()
    services = set(service_targets())
    catalog = ServiceCatalog(ROOT_DIR)
    infra = catalog.platform.get("infra")
    for section in sections:
        if section in services:
            declared = [Field(**field) for field in catalog.get(section).setup_fields]
        elif section.startswith("infra:"):
            group = section.split(":", 1)[1]
            declared = [
                Field(**{
                    key: value for key, value in field.items()
                    if key in Field.__dataclass_fields__
                })
                for field in infra.setup_fields
                if field["shared_group"] == group
            ]
        else:
            declared = CONFIG_FIELDS.get(section, [])
        for field in declared:
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


def print_credential_notices(changed, fields):
    notices = [field.change_notice for field in fields
               if field.name in changed and field.change_notice]
    if notices:
        print()
        for notice in notices:
            print(notice)


def print_generated_notices(generated_keys, fields):
    notices = [field.generated_notice for field in fields
               if field.name in generated_keys and field.generated_notice]
    if notices:
        print()
        for notice in notices:
            print(notice)


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
    generated = SECRETS.generate_values(generate_keys, values, target)

    updates = {}
    updates.update({
        key: value
        for key, value in chosen.items()
        if value != "__GENERATE__"
        and not (value == values.get(key) and is_real_value(key, values))
    })
    updates.update(generated)

    changed, _kept, backup = update_settings(updates)

    print_summary(changed, set(generated), backup)
    print_generated_notices(set(generated), fields)
    print_credential_notices(changed, fields)
    print()
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
