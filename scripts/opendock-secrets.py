#!/usr/bin/env python3
"""Select and generate OpenDock secrets through service declarations."""

import secrets
import string
import subprocess
import sys
import os
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from opendock_root import resolve_root
from opendock_capabilities import (
    SecretGenerationContext,
    SecretPlanningContext,
    generate_secrets as generate_service_secrets,
    has_capability,
    plan_secrets as plan_service_secrets,
)
from opendock_catalog import ServiceCatalog, ServiceDefinition
from opendock_groups import group_services, validate_services
import opendock_settings as SETTINGS


ROOT_DIR = resolve_root(__file__)


@dataclass(frozen=True)
class SelectedSecret:
    owner: str
    definition: Mapping[str, object]


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
    return list(ServiceCatalog(ROOT_DIR).names)


def selected_services(target):
    catalog = ServiceCatalog(ROOT_DIR)
    known = catalog.names
    platform_names = {component.name for component in catalog.platform.components}
    if target in ("all", "services"):
        return known
    if target in platform_names or target in SETTINGS.SHARED_CONFIG_SECTIONS:
        return []
    if target in known:
        return [target]
    group = group_services(target)
    if group:
        validate_services(group)
        return group
    raise SystemExit(f"Unknown target: {target}")


def selected_secrets(target):
    catalog = ServiceCatalog(ROOT_DIR)
    services = selected_services(target)
    selected: dict[str, SelectedSecret] = {}

    def add(owner, definition):
        key = definition["name"]
        if definition["kind"] not in {"generated-secret", "initial-credential"}:
            return
        existing = selected.get(key)
        if existing and existing.definition != definition:
            raise SystemExit(f"Conflicting secret declarations for {key}.")
        selected[key] = SelectedSecret(owner, MappingProxyType(dict(definition)))

    shared_groups = set()
    for component in catalog.platform.components:
        if target in ("all", component.name):
            shared_groups.update(component.shared_groups)
    for service in services:
        shared_groups.update(catalog.get(service).setup_dependencies)
    for component in catalog.platform.components:
        for field in component.setup_fields:
            if field.get("shared_group") in shared_groups:
                add(component.name, field)

    for name in services:
        for field in catalog.get(name).setup_fields:
            add(name, field)
    return services, selected


def _service_settings(service: ServiceDefinition, values: Mapping[str, str]) -> dict[str, str]:
    prefix = service.name.replace("-", "_").upper() + "_"
    return {key: value for key, value in values.items() if key.startswith(prefix)}


def _docker_capture(image, *command, input_text=None):
    docker_command = ["docker", "run", "--rm"]
    if input_text is not None:
        docker_command.append("-i")
    docker_command.extend([image, *command])
    try:
        result = subprocess.run(
            docker_command,
            check=True,
            text=True,
            input=input_text,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError as error:
        raise SystemExit("Docker is required to generate this service's secrets.") from error
    except subprocess.CalledProcessError as error:
        # Generator output can contain sensitive material. Never echo it on failure.
        raise SystemExit(
            f"Secret generation container failed for image {image} (exit {error.returncode})."
        ) from error
    return result.stdout.strip()


def generated_initial_credential(length=20):
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _generic_value(definition):
    kind = definition["kind"]
    generator = definition.get("generator", "url-safe")
    length = definition.get("length")
    if kind == "initial-credential":
        return generated_initial_credential(length or 20)
    if generator == "url-safe":
        return secrets.token_urlsafe(length or 36)
    if generator == "alphanumeric":
        alphabet = string.ascii_letters + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(length or 48))
    if generator == "hex":
        return secrets.token_hex(length or 32)
    return None


def generate_values(needed, existing, target="all", *, selected=None, services=None):
    """Generate generic fields and delegate custom bundles to service code."""
    if selected is None or services is None:
        services, selected = selected_secrets(target)
    unknown = set(needed) - set(selected)
    if unknown:
        raise SystemExit("Secret request contains undeclared keys: " + ", ".join(sorted(unknown)))
    needed = set(needed)
    if not needed:
        return {}

    builtin_generators = ServiceCatalog.BUILTIN_GENERATORS
    catalog = ServiceCatalog(ROOT_DIR)
    for service_name in services:
        definition = catalog.get(service_name)
        service_keys = frozenset(
            key for key, field in selected.items()
            if field.owner == service_name
        )
        if not service_keys or not has_capability(definition, "plan_secrets"):
            continue
        context = SecretPlanningContext(
            service=definition,
            selected_keys=service_keys,
            settings=MappingProxyType(_service_settings(definition, existing)),
        )
        needed.update(plan_service_secrets(context).keys)

    generated = {}
    delegated: dict[str, set[str]] = {}
    for key in sorted(needed):
        item = selected[key]
        generator = item.definition.get("generator", "url-safe")
        if generator not in builtin_generators:
            delegated.setdefault(item.owner, set()).add(key)
            continue
        generated[key] = _generic_value(item.definition)

    generated = {key: value for key, value in generated.items() if value is not None}
    for service_name, requested in delegated.items():
        definition = catalog.get(service_name)
        settings = _service_settings(definition, existing)
        settings.update({
            key: value for key, value in generated.items()
            if key.startswith(service_name.replace("-", "_").upper() + "_")
        })
        quiet = os.environ.get("OPEN_DOCK_QUIET_SECRETS") == "1"
        context = SecretGenerationContext(
            service=definition,
            requested_keys=frozenset(requested),
            settings=MappingProxyType(settings),
            run_image=_docker_capture,
            report=(lambda message: print(f"==> {service_name}: {message}")
                    if not quiet else None),
        )
        generated.update(generate_service_secrets(context))

    missing_results = needed - set(generated)
    if missing_results:
        raise SystemExit(
            "No secret generator is registered for: " + ", ".join(sorted(missing_results))
        )
    return generated


def update_config(generated):
    changed = SETTINGS.write_values(generated)
    return changed, SETTINGS.BACKUPS_CREATED[:]


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "all"
    quiet = os.environ.get("OPEN_DOCK_QUIET_SECRETS") == "1"
    services, selected = selected_secrets(target)
    selected_keys = set(selected)

    SETTINGS.initialize()
    existing = SETTINGS.load_values(process_env=False)
    needed = {
        key for key in selected_keys if is_placeholder(existing.get(key, ""))
    }
    if not needed:
        if not quiet:
            print("Generated secrets already exist in OpenDock config. Nothing changed.")
        return 0

    generated = generate_values(
        needed, existing, target, selected=selected, services=services
    )
    changed, backup = update_config(generated)
    if not quiet:
        print()
        if changed:
            print("Updated OpenDock configuration:")
            for key in sorted(changed):
                print(f"  {key}")
        if backup:
            print()
            for path in backup:
                print(f"Backup: {path.relative_to(ROOT_DIR)}")
        notices = [selected[key].definition.get("generated_notice")
                   for key in changed
                   if key in selected and selected[key].definition.get("generated_notice")]
        if notices:
            print()
            for notice in notices:
                print(notice)
        print()
        print("Done. Generated values were not printed; see the corresponding owner-specific .env file.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130) from None
