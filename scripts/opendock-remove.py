#!/usr/bin/env python3
"""Plan and remove one service's declared OpenDock resources."""

import errno
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from opendock_catalog import ServiceCatalog
from opendock_settings import (
    CONFIG, LEGACY_ENV, compose_env_files, initialize, load_values,
)
from opendock_storage import (
    external_paths_for_removal,
    resolve_mount_source,
    symlink_component,
)


ROOT = Path(__file__).resolve().parents[1]


class RemovalError(Exception):
    pass


def run_command(args, *, capture=False, check=True, input_text=None):
    try:
        result = subprocess.run(
            [str(arg) for arg in args], cwd=ROOT, text=True,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None, input=input_text, check=False,
        )
    except FileNotFoundError as exc:
        raise RemovalError(f"Required command not found: {exc.filename}") from exc
    if check and result.returncode:
        detail = result.stderr.strip() if capture and result.stderr else ""
        raise RemovalError(detail or f"Command failed ({result.returncode}): {args[0]}")
    return result


def parse_env(path):
    values = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def domains_module():
    path = ROOT / "scripts" / "opendock-domains.py"
    spec = importlib.util.spec_from_file_location("opendock_domains_for_remove", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def compose_prefix(service):
    directory = ROOT / "services" / service
    command = ["docker", "compose", "--project-directory", directory]
    for env_file in compose_env_files(service):
        command += ["--env-file", env_file]
    return command + ["-f", directory / "compose.yml", "-p", service]


def infra_compose_prefix():
    directory = ROOT / "infra"
    command = ["docker", "compose", "--project-directory", directory]
    for env_file in compose_env_files("infra"):
        command += ["--env-file", env_file]
    return command + ["-f", directory / "compose.yml", "-p", "infra"]


def database_removal_request(adapter_file, adapter, container, database, role):
    path = ROOT / adapter_file
    module_name = f"_opendock_database_adapter_{adapter}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RemovalError(f"Could not load shared database adapter: {adapter}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        handler = getattr(module, "removal_request", None)
        if not callable(handler):
            raise RemovalError(
                f"Shared database adapter {adapter!r} has no removal_request operation."
            )
        result = handler(container, database, role)
    except RemovalError:
        raise
    except Exception as exc:
        raise RemovalError(f"Shared database adapter {adapter!r} failed: {exc}") from exc
    if (
        not isinstance(result, tuple)
        or len(result) != 2
        or not isinstance(result[0], (list, tuple))
        or any(not isinstance(argument, str) for argument in result[0])
        or not isinstance(result[1], str)
    ):
        raise RemovalError(
            f"Shared database adapter {adapter!r} returned an invalid removal request."
        )
    return list(result[0]), result[1]


def resolve_shared_database(service, catalog, settings):
    definition = catalog.get(service)
    declaration = definition.removal.get("shared_database")
    if not declaration:
        return None
    group = declaration["shared_group"]
    database_name = settings.get(declaration["database_key"], "").strip()
    role_name = settings.get(declaration["role_key"], "").strip()
    if not database_name or not role_name:
        raise RemovalError(
            f"{definition.display_name} database ownership settings are incomplete; "
            "cannot safely remove shared database objects."
        )
    if not re.fullmatch(r"[A-Za-z0-9_]{1,63}", database_name) or not re.fullmatch(
        r"[A-Za-z0-9_]{1,63}", role_name
    ):
        raise RemovalError(
            f"{definition.display_name} database or role name contains unsupported characters; "
            "cannot safely build a scoped removal statement."
        )

    for other in catalog.services:
        if other.name == service or group not in other.setup_dependencies:
            continue
        other_declaration = other.removal.get("shared_database")
        if not other_declaration or other_declaration.get("shared_group") != group:
            raise RemovalError(
                f"Cannot safely remove the {group} database for {definition.display_name}: "
                f"{other.display_name} also uses this shared database group but has no "
                "audited database removal declaration yet."
            )
        other_settings = load_values(service=other.name, process_env=False)
        other_database = other_settings.get(other_declaration["database_key"], "").strip()
        other_role = other_settings.get(other_declaration["role_key"], "").strip()
        if (
            database_name.casefold() == other_database.casefold()
            or role_name.casefold() == other_role.casefold()
        ):
            raise RemovalError(
                f"Cannot safely remove {database_name}/{role_name}: it is also configured "
                f"for {other.display_name}. Choose distinct database and role names first."
            )

    adapter_owner = next(
        (
            (component, item)
            for component in catalog.platform.components
            for item in component.shared_databases
            if item["shared_group"] == group
        ),
        None,
    )
    if adapter_owner is None:
        raise RemovalError(f"No platform database adapter is registered for {group}.")
    component, adapter = adapter_owner
    return {
        "group": group,
        "engine": adapter["engine"],
        "adapter": adapter["adapter"],
        "adapter_file": str(
            (component.directory / "adapters" / f"{adapter['adapter']}.py")
            .relative_to(ROOT)
        ),
        "container": adapter["container"],
        "database": database_name,
        "role": role_name,
    }


def routes_for_removal(domains):
    if domains.DOMAINS_FILE.is_file():
        return domains.parse_domains_file()
    if CONFIG.joinpath("core.env").is_file() or LEGACY_ENV.is_file():
        return domains.default_routes()
    return []


def owned_path(service, relative):
    service_root = (ROOT / "services" / service).resolve()
    current = ROOT / "services" / service
    for part in Path(relative).parts:
        current = current / part
        if current.is_symlink():
            raise RemovalError(f"Refusing to access declared removal path through a symlink: {current}")
    resolved = current.resolve()
    try:
        resolved.relative_to(service_root)
    except ValueError as exc:
        raise RemovalError(f"Declared removal path escapes services/{service}: {relative}") from exc
    return current


def inspect_orphan_containers(service, declarations, compose_ids):
    candidates = {}
    for declaration in declarations:
        label = declaration["label"]
        raw_ids = run_command(
            ["docker", "ps", "-aq", "--filter", f"label={label}"], capture=True
        ).stdout.splitlines()
        candidates.update({item.strip(): declaration for item in raw_ids if item.strip()})
    candidates = {item: spec for item, spec in candidates.items() if item not in compose_ids}
    if not candidates:
        return []

    inspected = json.loads(run_command(
        ["docker", "inspect", *candidates], capture=True
    ).stdout)
    owned = []
    for container in inspected:
        container_id = container.get("Id", "")
        declaration = candidates.get(container_id)
        if not declaration:
            continue
        expected_root = owned_path(service, declaration["path"]).resolve()
        for mount in container.get("Mounts", []):
            source = mount.get("Source")
            if not source:
                continue
            resolved = Path(source).resolve()
            try:
                resolved.relative_to(expected_root)
            except ValueError:
                continue
            owned.append({
                "id": container_id,
                "name": container.get("Name", "").lstrip("/"),
                "image": container.get("Config", {}).get("Image", ""),
                "path": declaration["path"],
            })
            break
    return owned


def build_plan(service):
    catalog = ServiceCatalog(ROOT)
    definition = catalog.get(service)
    removal = definition.removal
    if not removal:
        raise RemovalError(
            f"Removal is not registered for {definition.display_name}. "
            "This service must declare its resource ownership before it can be removed."
        )
    service_dir = definition.directory
    service_config = service_dir / ".env"
    legacy_service_config = CONFIG / "services" / f"{service}.env"
    domains = domains_module()
    if CONFIG.is_symlink() or service_dir.is_symlink():
        raise RemovalError(f"Refusing to inspect {service} configuration through a symlink.")
    if service_config.is_symlink() or legacy_service_config.is_symlink():
        raise RemovalError(f"Refusing to edit {service} configuration through a symlink.")
    if LEGACY_ENV.is_symlink():
        raise RemovalError("Refusing to migrate legacy config through a symlink.")
    if domains.DOMAINS_FILE.is_symlink():
        raise RemovalError("Refusing to edit domains.conf because it is a symlink.")

    declared_paths = list(removal.get("data_paths", ()))
    paths = {relative: owned_path(service, relative) for relative in declared_paths}
    preserved_paths = []
    for relative in removal.get("preserve_paths", ()):
        path = owned_path(service, relative)
        if path.exists():
            preserved_paths.append(relative)
    declared_config_files = list(removal.get("config_files", ()))
    config_files = []
    for relative in declared_config_files:
        path = owned_path(service, relative)
        if path.is_symlink():
            raise RemovalError(
                f"Refusing to remove declared config through a symlink: {path}"
            )
        if path.exists() and not path.is_file():
            raise RemovalError(
                f"Declared private config is not a regular file: {path}"
            )
        if path.is_file():
            config_files.append(relative)
    all_routes = routes_for_removal(domains)
    routes = [route for route in all_routes
              if route.get("type") == "docker" and route.get("target") == service]
    compose_ids = {
        item.strip() for item in run_command(
            ["docker", "ps", "-aq", "--filter",
             f"label=com.docker.compose.project={service}"], capture=True,
        ).stdout.splitlines() if item.strip()
    }
    orphan_containers = inspect_orphan_containers(
        service, removal.get("orphan_containers", ()), compose_ids
    )
    volumes = [item.strip() for item in run_command(
        ["docker", "volume", "ls", "--filter",
         f"label=com.docker.compose.project={service}", "--format", "{{.Name}}"],
        capture=True,
    ).stdout.splitlines() if item.strip()]
    images = [item.strip() for item in run_command(
        [*compose_prefix(service), "config", "--images"], capture=True,
    ).stdout.splitlines() if item.strip()]
    images.extend(removal.get("extra_images", ()))
    images = list(dict.fromkeys(images))

    prefix = service.replace("-", "_").upper() + "_"
    service_values = parse_env(service_config)
    old_values = parse_env(legacy_service_config)
    legacy_values = parse_env(LEGACY_ENV)
    configured_keys = sorted(
        key for source in (service_values, old_values, legacy_values)
        for key in source if key.startswith(prefix)
    )
    configured_keys = sorted(set(configured_keys))
    settings = load_values(service=service, process_env=False)
    external_storage = external_paths_for_removal(definition, settings)
    for owned in external_storage:
        if not owned["exists"]:
            continue
        target_path = owned["path"].resolve()
        for other in catalog.services:
            if other.name == service:
                continue
            other_values = load_values(service=other.name, process_env=False)
            for other_mount in other.storage_mounts:
                try:
                    other_path = resolve_mount_source(other, other_mount, other_values).resolve()
                except (KeyError, ValueError):
                    continue
                if (
                    target_path == other_path
                    or target_path in other_path.parents
                    or other_path in target_path.parents
                ):
                    raise RemovalError(
                        f"Cannot remove {target_path}; it overlaps the configured "
                        f"{other.display_name} storage path {other_path}."
                    )
    shared_database = resolve_shared_database(service, catalog, settings)
    custom_data = [
        relative for relative, path in paths.items() if path.exists()
    ]

    return {
        "service": definition,
        "domains": domains,
        "routes": routes,
        "compose_ids": sorted(compose_ids),
        "orphan_containers": orphan_containers,
        "volumes": volumes,
        "images": images,
        "data_paths": custom_data,
        "external_storage": external_storage,
        "preserve_paths": preserved_paths,
        "config_files": config_files,
        "shared_database": shared_database,
        "configured_keys": configured_keys,
        "remove_service_config": service_config.exists() or legacy_service_config.exists(),
        "migrate_legacy_config": LEGACY_ENV.is_file(),
    }


def print_plan(plan):
    definition = plan["service"]
    name = definition.name
    print(f"Complete removal plan for {definition.display_name}:")
    print(f"  Stop and remove {definition.display_name} Compose containers")
    if plan["compose_ids"]:
        print(f"    {len(plan['compose_ids'])} Compose container(s)")
    else:
        print("    (none currently present)")
    print(f"  Remove {definition.display_name} service-specific containers:")
    if plan["orphan_containers"]:
        for item in plan["orphan_containers"]:
            print(f"    {item['name']} ({item['image']}; services/{name}/{item['path']}/)")
    else:
        print("    (none found in declared service data paths)")
    print(f"  Remove {definition.display_name} Compose named volumes:")
    for volume in plan["volumes"] or ["(none currently present)"]:
        print(f"    {volume}")
    print(f"  Remove {definition.display_name} images if not in use by another container:")
    for image in plan["images"] or ["(none declared)"]:
        print(f"    {image}")
    print(f"  Remove {definition.display_name} public routes and Cloudflare Tunnel/DNS entries:")
    for route in plan["routes"] or [{"hostname": "(none configured)"}]:
        print(f"    {route['hostname']}")
    if not (ROOT / "cloudflare.env").is_file():
        print("    Cloudflare API cleanup unavailable; cloudflare.env is absent")
    if plan["shared_database"]:
        database = plan["shared_database"]
        print(
            f"  Remove only this service's {database['engine']} database and role "
            f"from shared {database['group']}:"
        )
        print(f"    database: {database['database']}")
        print(f"    role: {database['role']}")
    for relative in plan["data_paths"]:
        print(f"  Delete declared service data: services/{name}/{relative}/")
        for preserved in plan["preserve_paths"]:
            if Path(preserved).is_relative_to(Path(relative)):
                print(f"    Preserve: services/{name}/{preserved}")
    for item in plan.get("external_storage", []):
        state = "" if item["exists"] else " (not present)"
        print(
            f"  Delete configured {item['mount']['name']} storage directory: "
            f"{item['path']}{state}"
        )
    if plan["config_files"]:
        print(f"  Remove additional private configuration for {definition.display_name}:")
        for relative in plan["config_files"]:
            print(f"    services/{name}/{relative}")
        print("    A permission-restricted backup will be retained.")
    print(f"  Remove {definition.display_name} settings from services/{name}/.env:")
    for key in plan["configured_keys"] or ["(none configured)"]:
        print(f"    {key}")
    if plan["remove_service_config"]:
        print("    A permission-restricted service config backup will be retained.")
    if plan["migrate_legacy_config"]:
        print("  Migrate remaining common.env values to their owner files and retain its backup.")
    print("  Preserve OpenDock code, core/shared settings, shared infra, and Caddy state.")


def remove_shared_database(plan):
    database = plan["shared_database"]
    if not database:
        return
    container = database["container"]
    running = run_command(
        ["docker", "inspect", "--format", "{{.State.Running}}", container],
        capture=True,
        check=False,
    )
    if running.returncode or running.stdout.strip().lower() != "true":
        run_command([*infra_compose_prefix(), "up", "-d", container])

    command, sql = database_removal_request(
        database["adapter_file"], database["adapter"], container,
        database["database"], database["role"]
    )
    run_command(command, capture=True, input_text=sql)
    print(
        f"Removed shared {database['group']} database objects for "
        f"{plan['service'].display_name}: "
        f"{database['database']}, {database['role']}."
    )


def backup_service_config(service, service_config):
    relative = service_config.relative_to(ROOT / "services" / service)
    backup_dir = ROOT / "backups" / "config" / "services" / service / relative.parent
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup = backup_dir / f"{relative.name}.{timestamp}.bak"
    shutil.copy2(service_config, backup)
    backup.chmod(0o600)
    return backup


def remove_service_config(service):
    service_config = ROOT / "services" / service / ".env"
    if not service_config.is_file():
        return
    if service_config.is_symlink():
        raise RemovalError(f"Refusing to remove service configuration symlink: {service_config}")
    backup_service_config(service, service_config)
    service_config.unlink()


def remove_additional_config_file(service, relative):
    path = owned_path(service, relative)
    if not path.is_file():
        return
    if path.is_symlink():
        raise RemovalError(f"Refusing to remove service config symlink: {path}")
    backup = backup_service_config(service, path)
    path.unlink()
    print(
        f"Removed services/{service}/{relative}; "
        f"restricted backup: {backup.relative_to(ROOT)}"
    )


def remove_routes(service, plan):
    if not plan["routes"]:
        return
    domains = plan["domains"]
    current = routes_for_removal(domains)
    current_routes = [route for route in current
                      if route.get("type") == "docker" and route.get("target") == service]
    if not current_routes:
        return
    for route in current_routes:
        run_command([sys.executable, ROOT / "scripts" / "publish-cloudflare.py",
                     "remove", route["hostname"]])
    remaining = [route for route in current if not (
        route.get("type") == "docker" and route.get("target") == service)]
    domains.save_routes(remaining)
    domains.render_routes(remaining)
    names = run_command(["docker", "ps", "--format", "{{.Names}}"],
                        capture=True, check=False)
    if names.returncode == 0 and "caddy" in names.stdout.splitlines():
        reload_result = run_command(
            ["docker", "exec", "caddy", "caddy", "reload", "--config", "/etc/caddy/Caddyfile"],
            capture=True, check=False,
        )
        if reload_result.returncode:
            print("Warning: local route file changed, but Caddy reload failed. "
                  "Restart the gateway to apply it.")
    else:
        print("Caddy is not running; the removed route will stay absent on next launch.")


def remove_path_preserving(path, preserve):
    if path in preserve:
        return
    if path.is_symlink() or not path.is_dir():
        if path.exists() or path.is_symlink():
            path.unlink()
        return
    for child in path.iterdir():
        remove_path_preserving(child, preserve)
    try:
        path.rmdir()
    except OSError as exc:
        # A non-empty directory contains a declared preserved path.
        if exc.errno not in (errno.ENOTEMPTY, errno.EEXIST):
            raise


def remove_declared_data(service, relative, preserve_paths=()):
    path = owned_path(service, relative)
    if not path.exists():
        return
    preserve = {owned_path(service, item) for item in preserve_paths}
    remove_path_preserving(path, preserve)
    if preserve:
        print(f"Removed services/{service}/{relative} except declared preserved paths.")
    else:
        print(f"Removed services/{service}/{relative}/")


def remove_external_storage(items):
    for item in items:
        path = Path(item["path"])
        if not path.exists() and not path.is_symlink():
            continue
        linked = symlink_component(path)
        if linked:
            raise RemovalError(f"Refusing to remove storage path through a symlink: {linked}")
        if not path.is_dir() or path.is_mount():
            raise RemovalError(
                f"Refusing to remove configured storage path that is not a regular directory: {path}"
            )
        resolved = path.resolve()
        home = Path.home().resolve()
        if resolved == Path(resolved.anchor) or resolved == home or home.is_relative_to(resolved):
            raise RemovalError(f"Refusing to remove a filesystem root or home directory: {path}")
        shutil.rmtree(path)
        print(f"Removed external storage directory: {path}")


def remove_resources(plan):
    definition = plan["service"]
    service = definition.name
    initialize()
    if plan["shared_database"]:
        if plan["compose_ids"]:
            run_command([*compose_prefix(service), "stop"])
    run_command([*compose_prefix(service), "down", "--volumes", "--remove-orphans"])

    orphan_ids = [item["id"] for item in plan["orphan_containers"] if item.get("id")]
    if orphan_ids:
        run_command(["docker", "rm", "-f", *orphan_ids])

    # Remove the route and shared database objects only after containers are
    # cleanly removed. A Compose/API failure must not leave a running service
    # without its route or database.
    remove_routes(service, plan)
    remove_shared_database(plan)

    for relative in plan["data_paths"]:
        preserved = [
            item for item in plan["preserve_paths"]
            if Path(item).is_relative_to(Path(relative))
        ]
        remove_declared_data(service, relative, preserved)
    remove_external_storage(plan.get("external_storage", []))
    remove_service_config(service)
    for relative in plan["config_files"]:
        remove_additional_config_file(service, relative)

    for image in plan["images"]:
        result = run_command(["docker", "image", "rm", image], capture=True, check=False)
        if result.returncode:
            detail = (result.stderr or result.stdout or "image is absent or in use").strip()
            print(f"Kept image {image}: {detail}")
        else:
            print(f"Removed image {image}")
    print(f"{definition.display_name} removal complete. Run './opendock launch {service}' to set it up again.")


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) not in (1, 2) or (len(args) == 2 and args[1] != "--dry-run"):
        print("Usage: ./opendock remove <service> [--dry-run]", file=sys.stderr)
        return 2
    service = args[0]
    try:
        plan = build_plan(service)
        print_plan(plan)
        if len(args) == 2:
            print("Dry run: no changes made.")
            return 0
        if not sys.stdin.isatty():
            raise RemovalError("Removal requires an interactive confirmation; no changes were made.")
        print()
        print(f"This permanently deletes {plan['service'].display_name} settings, data, and configured public routes.")
        confirmation = input(f"Type REMOVE {service} to continue: ")
        if confirmation != f"REMOVE {service}":
            print("Removal cancelled. No changes made.")
            return 0
        remove_resources(plan)
    except (RemovalError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"OpenDock remove: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
