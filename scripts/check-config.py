#!/usr/bin/env python3
import os
import importlib.util
import re
import sys
from pathlib import Path

from opendock_groups import group_services, validate_services
from opendock_catalog import ServiceCatalog, service_names
from opendock_capabilities import ValidationContext, runtime_environment, validate_config
from opendock_settings import (
    CONFIG_SECTIONS, CORE_PLACEHOLDERS, CORE_REQUIRED_KEYS, load_values,
)
from opendock_storage import validate_mounts


ROOT_DIR = Path(__file__).resolve().parents[1]
DOMAIN_SPEC = importlib.util.spec_from_file_location(
    "opendock_domains", ROOT_DIR / "scripts" / "opendock-domains.py"
)
DOMAINS = importlib.util.module_from_spec(DOMAIN_SPEC)
DOMAIN_SPEC.loader.exec_module(DOMAINS)
TARGET = sys.argv[1] if len(sys.argv) > 1 else "all"
QUIET = os.environ.get("CHECK_CONFIG_QUIET") == "1"
INTERPOLATION_RE = re.compile(
    r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?:(:?[-?=+])([^}]*))?\}"
)
GLOBAL_REQUIRED = CORE_REQUIRED_KEYS
def service_targets():
    return list(service_names(ROOT_DIR))


def target_dir(target):
    if target in ("infra", "gateway"):
        return ROOT_DIR / target
    return ServiceCatalog(ROOT_DIR).get(target).directory


def all_targets():
    targets = ["infra"]
    if (ROOT_DIR / "gateway" / "compose.yml").is_file():
        targets.append("gateway")
    targets.extend(service_targets())
    return targets


def resolve_targets(target):
    if target == "all":
        return [*all_targets(), "cloudflare"]
    if target in CONFIG_SECTIONS and target != "core":
        return [target]
    if target == "services":
        return service_targets()
    if target in ("infra", "gateway"):
        return [target]

    if target in service_targets():
        return [target]

    group = group_services(target)
    if group:
        validate_services(group)
        return group

    raise SystemExit(f"Service '{target}' is not installed. Install its OpenDock package first.")


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

    if name in CORE_PLACEHOLDERS and value == CORE_PLACEHOLDERS[name]:
        return True

    if re.search(r"(PASSWORD|SECRET|TOKEN|KEY)", name):
        normalized = value.strip().lower()
        if normalized.startswith("change") or normalized in {"changeme", "password"}:
            return True
        if example_values.get(name) == value:
            return True

    return False


def generated_fields_for_target(target):
    """Return generated credentials owned by the target's config descriptors."""
    generated = set()
    shared_groups = set()
    catalog = ServiceCatalog(ROOT_DIR)
    components = {item.name: item for item in catalog.platform.components}
    if target in CONFIG_SECTIONS:
        fields = CONFIG_SECTIONS[target].get("setup", {}).get("fields", [])
        generated.update(
            field["name"] for field in fields
            if field.get("kind") in {"generated-secret", "initial-credential"}
        )
    elif target in components:
        component = components[target]
        fields = component.setup_fields
        shared_groups.update(component.shared_groups)
        generated.update(
            field["name"] for field in fields
            if field.get("kind") in {"generated-secret", "initial-credential"}
        )
    elif target in catalog.names:
        service = catalog.get(target)
        shared_groups.update(service.setup_dependencies)
        generated.update(
            field["name"] for field in service.setup_fields
            if field.get("kind") in {"generated-secret", "initial-credential"}
        )
    for component in catalog.platform.components:
        generated.update(
            field["name"] for field in component.setup_fields
            if field.get("shared_group") in shared_groups
            and field.get("kind") in {"generated-secret", "initial-credential"}
        )
    return generated


def check_target(target, common_values, example_values):
    generated = generated_fields_for_target(target)
    if target in CONFIG_SECTIONS:
        fields = CONFIG_SECTIONS[target].get("setup", {}).get("fields", [])
        required = {
            field["name"] for field in fields
            if field.get("required") is True
            or field.get("kind") in {
                "required-user", "secret-user", "initial-credential", "generated-secret"
            }
        }
        missing = sorted(name for name in required if not common_values.get(name))
        placeholders = sorted(
            name for name in required
            if common_values.get(name)
            and is_placeholder(name, common_values.get(name, ""), example_values)
        )
        return {
            "target": target,
            "missing": missing,
            "placeholders": placeholders,
            "invalid": [],
            "optional": {},
            "generated": generated,
        }

    directory = target_dir(target)
    compose = directory / "compose.yml"
    if not compose.is_file():
        return {
            "target": target,
            "missing": [f"compose.yml for {target}"],
            "placeholders": [],
            "invalid": [],
            "optional": {},
            "generated": generated,
        }

    env = {}
    env.update(common_values)

    definition = None
    if target in service_targets():
        definition = ServiceCatalog(ROOT_DIR).get(target)
        try:
            env.update(runtime_environment(
                definition,
                docker_socket=os.environ.get("DOCKER_SOCKET", "/var/run/docker.sock"),
            ))
        except ValueError as error:
            raise SystemExit(str(error)) from error

    required, optional = compose_variables(compose)
    required.update(GLOBAL_REQUIRED)
    if definition:
        required.update(
            field["name"]
            for field in definition.setup_fields
            if field.get("required") is True or field.get("kind") == "required-user"
        )
    missing = sorted(name for name in required if not env.get(name))
    placeholders = sorted(
        name
        for name in required
        if name in env and is_placeholder(name, env.get(name, ""), example_values)
    )
    invalid = []
    if definition:
        prefix = target.replace("-", "_").upper() + "_"
        service_settings = {
            name: value for name, value in env.items() if name.startswith(prefix)
        }
        service_examples = {
            name: value for name, value in example_values.items()
            if name.startswith(prefix)
        }
        try:
            invalid.extend(validate_config(ValidationContext(
                service=definition,
                settings=service_settings,
                examples=service_examples,
            )).issues)
        except ValueError as error:
            raise SystemExit(str(error)) from error
        invalid.extend(validate_mounts(definition, env))

    optional_missing = {}
    target_subdomain = definition.routing.get("subdomain_key") if definition else None
    for name, default in sorted(optional.items()):
        if name in env or not target_subdomain or name != target_subdomain:
            continue
        optional_missing[name] = default

    return {
        "target": target,
        "missing": missing,
        "placeholders": placeholders,
        "invalid": invalid,
        "optional": optional_missing,
        "generated": generated,
    }


def print_results(results):
    failed = False

    for result in results:
        target = result["target"]
        missing = result["missing"]
        placeholders = result["placeholders"]
        invalid = result["invalid"]
        optional = result["optional"]
        should_print = not QUIET or missing or placeholders or invalid

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

        if invalid:
            failed = True
            print("Invalid or inconsistent values:")
            for name in invalid:
                print(f"  {name}")

        if optional and not QUIET:
            print("Optional values missing, defaults will be used:")
            for name, default in optional.items():
                print(f"  {name}={default}")

        if not missing and not placeholders and not invalid and not optional and not QUIET:
            print("OK")

        if should_print:
            print()

    if failed:
        print("Set external values with `./opendock setup` or `./opendock setup <service>`.")
        print(f"Run `./opendock setup {TARGET}` to review and fill user-facing values.")
        generated_missing = {
            name
            for result in results
            for name in result.get("generated", set())
            if name in set(result["missing"]) | set(result["placeholders"])
        }
        if generated_missing:
            print("Run `./opendock secrets` to fill generated passwords and app secrets.")
        return 1

    return 0


def main():
    common_values = load_values(process_env=False)
    example_values = load_values(examples=True)
    targets = resolve_targets(TARGET)
    results = [check_target(target, common_values, example_values) for target in targets]
    failed = print_results(results)
    try:
        DOMAINS.resolve_routes()
    except SystemExit as error:
        print(f"Domain route configuration: {error}")
        failed = 1
    return failed


if __name__ == "__main__":
    raise SystemExit(main())
