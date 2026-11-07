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
    placeholder: Optional[str] = None
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
    name: [Field(**field) for field in section.get("setup", {}).get("fields", [])]
    for name, section in SETTINGS.CONFIG_SECTIONS.items()
}


def service_targets():
    return list(service_names(ROOT_DIR))


def resolve_sections(target):
    catalog = ServiceCatalog(ROOT_DIR)
    platform_components = {component.name for component in catalog.platform.components}
    if target == "all":
        services = service_targets()
    elif target == "services":
        services = service_targets()
    elif target in platform_components or target in CONFIG_FIELDS:
        services = []
    elif target in catalog.names:
        services = [target]
    else:
        group = group_services(target)
        if not group:
            raise SystemExit(
                f"Service '{target}' is not installed. Install its OpenDock package first."
            )
        validate_services(group)
        services = group

    sections = [] if target in SETTINGS.SHARED_CONFIG_SECTIONS else ["core"]
    shared_setup = {
        dependency
        for service in services
        for dependency in catalog.get(service).setup_dependencies
    }
    platform_by_group = {}
    for component in catalog.platform.components:
        for group in component.shared_groups:
            platform_by_group[group] = component
            if target in (component.name, "all"):
                shared_setup.add(group)
    sections.extend(
        f"{platform_by_group[group].name}:{group}"
        for group in sorted(shared_setup)
        if group in platform_by_group
    )
    if target in SETTINGS.CONFIG_SECTIONS and target != "core":
        sections.append(target)
    if target == "all":
        sections.append("cloudflare")

    for service in services:
        sections.append(service)

    return sections


def optional_configs_for(sections):
    service_ids = set(service_targets())
    optional = []
    catalog = ServiceCatalog(ROOT_DIR)
    for service in sections:
        if service not in service_ids:
            continue
        for config_id in catalog.get(service).optional_setup_configs:
            if config_id not in SETTINGS.CONFIG_OPTIONAL_PROMPTS:
                raise SystemExit(
                    f"Service {service!r} declares unknown optional config {config_id!r}."
                )
            if config_id not in optional:
                optional.append(config_id)
    return optional


def optional_config_needed(config_id, values):
    skip_key = SETTINGS.CONFIG_OPTIONAL_SKIP_KEYS.get(config_id)
    if skip_key and values.get(skip_key, "").strip().lower() in {"1", "true", "yes"}:
        return False
    required_fields = [
        field for field in CONFIG_FIELDS[config_id]
        if field.kind in {"required-user", "secret-user", "initial-credential", "generated-secret"}
        or field.required is True
    ]
    return any(not is_real_value(field.name, values) for field in required_fields)


def offer_optional_configs(config_ids, values, *, selected):
    updates = {}
    for config_id in config_ids:
        if config_id in selected or not optional_config_needed(config_id, values):
            continue
        if not sys.stdin.isatty():
            print(
                f"Skipping optional {config_id} setup in non-interactive mode. "
                f"Run './opendock setup {config_id}' to configure it later."
            )
            continue
        prompt = SETTINGS.CONFIG_OPTIONAL_PROMPTS[config_id]
        answer = input(
            f"\nOptional setup ({config_id}): {prompt}\n"
            "Configure it now? [y/N] "
        ).strip().lower()
        if answer in ("y", "yes"):
            selected.append(config_id)
            skip_key = SETTINGS.CONFIG_OPTIONAL_SKIP_KEYS.get(config_id)
            if skip_key and values.get(skip_key, "").strip().lower() in {"1", "true", "yes"}:
                updates[skip_key] = "false"
        else:
            skip_key = SETTINGS.CONFIG_OPTIONAL_SKIP_KEYS.get(config_id)
            if skip_key:
                updates[skip_key] = "true"
            print(
                f"Skipping {config_id} setup; this choice is remembered and service startup will continue. "
                f"Run './opendock setup {config_id}' later to configure it."
            )
    return updates


def selected_fields(sections):
    fields = []
    seen = set()
    services = set(service_targets())
    catalog = ServiceCatalog(ROOT_DIR)
    for section in sections:
        if section in services:
            declared = [Field(**field) for field in catalog.get(section).setup_fields]
        elif ":" in section:
            component_name, group = section.split(":", 1)
            component = catalog.platform.get(component_name)
            declared = [
                Field(**{
                    key: value for key, value in field.items()
                    if key in Field.__dataclass_fields__
                })
                for field in component.setup_fields
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
    if name in SETTINGS.CORE_PLACEHOLDERS and value == SETTINGS.CORE_PLACEHOLDERS[name]:
        return False
    return not SECRETS.is_placeholder(value)


def prompt_required(field, values):
    print_field_note(field)
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
    print_field_note(field)
    current = values.get(field.name, "")
    default = current if is_real_value(field.name, values) else field.default
    if default:
        answer = input(f"{field.name} [{default}]: ").strip()
        return default if not answer else answer

    answer = input(f"{field.name}: ").strip()
    return answer


def prompt_initial_credential(field, values):
    print_field_note(field)
    if is_real_value(field.name, values):
        print(f"{field.name} [keep existing]")
        answer = input("  Enter a new value? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            return None
        value = input(f"  New {field.name} [auto-generate]: ").strip()
        return value or "__GENERATE__"

    if field.note:
        print(f"{field.name}")
    value = input(f"{field.name} [auto-generate]: ").strip()
    return value or "__GENERATE__"


def prompt_secret(field, values):
    print_field_note(field)
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


def print_field_note(field):
    if field.note:
        print(f"  {field.note}")


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
    internal_keys = set(SETTINGS.CONFIG_OPTIONAL_SKIP_KEYS.values())
    visible_changed = set(changed) - internal_keys
    print()
    if visible_changed:
        print("Updated OpenDock configuration:")
        for key in sorted(visible_changed):
            if key in generated_keys:
                print(f"  {key} generated")
            else:
                print(f"  {key}")
    elif changed:
        print("Optional setup preference saved; no service settings changed.")
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


def review_setup(target):
    sections = resolve_sections(target)
    SETTINGS.initialize()
    values = SETTINGS.load_values(process_env=False)
    fields = selected_fields(sections)
    print(f"OpenDock setup: {target} current service settings")
    if not fields:
        print("  This service has no user-facing setup fields.")
        return 0
    print()
    for field in fields:
        value = values.get(field.name, "") or field.default or ""
        if field.kind in {"secret-user", "initial-credential", "generated-secret"}:
            shown = "configured" if is_real_value(field.name, values) else "not set"
        else:
            shown = value if value else "not set"
        print(f"  {field.name}: {shown}")

    incomplete = [
        field for field in fields
        if field.kind in {"required-user", "secret-user", "initial-credential"}
        and not is_real_value(field.name, values)
    ]
    if incomplete:
        print("\nRequired service settings are incomplete; setup must be completed now.")
        return main([target])
    if not sys.stdin.isatty():
        print("\nNon-interactive launch: keeping the current service settings.")
        return 0
    answer = input("\nChange service settings before launch? [y/N] ").strip().lower()
    if answer in {"y", "yes"}:
        return main([target])
    return 0


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    review = "--review" in args
    if review:
        args.remove("--review")
    optional_only = "--optional-only" in args
    storage_only = "--storage-only" in args
    if sum((review, optional_only, storage_only)) > 1:
        raise SystemExit("--review, --optional-only, and --storage-only cannot be combined")
    args = [arg for arg in args if arg not in {"--optional-only", "--storage-only"}]
    if len(args) > 1:
        raise SystemExit(
            "Usage: opendock-config.py [--optional-only | --storage-only] [target]"
        )
    target = args[0] if args else "all"
    if review:
        if target not in service_targets():
            raise SystemExit("--review requires one installed service target")
        return review_setup(target)
    if storage_only and target not in service_targets():
        raise SystemExit("--storage-only requires one service target")
    sections = resolve_sections(target)
    optional_configs = [] if storage_only else optional_configs_for(sections)

    SETTINGS.initialize()
    values = SETTINGS.load_values(process_env=False)
    updates = {}
    if optional_only:
        # A launch check only offers configuration that is not already complete
        # and has not previously been skipped.
        offered = [name for name in optional_configs if optional_config_needed(name, values)]
        sections = []
        updates = offer_optional_configs(offered, values, selected=sections)
        if not sections:
            if updates:
                SETTINGS.write_values(updates)
            return 0
    else:
        updates = offer_optional_configs(optional_configs, values, selected=sections)
        if target in SETTINGS.SHARED_CONFIG_SECTIONS:
            skip_key = SETTINGS.CONFIG_OPTIONAL_SKIP_KEYS.get(target)
            if skip_key and values.get(skip_key, "").strip().lower() in {"1", "true", "yes"}:
                updates[skip_key] = "false"

    label = f"{target} storage location" if storage_only else target
    print(f"OpenDock setup: {'optional ' if optional_only else ''}{label}")
    print()
    print("Existing values are kept when you press Enter.")
    print("Secrets are generated or kept without printing their values.")
    print()

    fields = selected_fields(sections)
    services = set(service_targets())
    storage_keys = {
        mount["setting_key"]
        for service in sections
        if service in services
        for mount in ServiceCatalog(ROOT_DIR).get(service).storage_mounts
    }
    if storage_only:
        if not storage_keys:
            raise SystemExit(f"Service {target!r} does not declare configurable storage.")
        fields = [field for field in fields if field.name in storage_keys]

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

    chosen_updates = {
        key: value
        for key, value in chosen.items()
        if value != "__GENERATE__"
        and (
            key in storage_keys
            or not (value == values.get(key) and is_real_value(key, values))
        )
    }
    updates.update(chosen_updates)
    updates.update(generated)

    changed, _kept, backup = update_settings(updates)

    print_summary(changed, set(generated), backup)
    print_generated_notices(set(generated), fields)
    print_credential_notices(changed, fields)
    print()
    print("Done.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130) from None
