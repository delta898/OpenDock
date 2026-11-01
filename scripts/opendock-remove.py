#!/usr/bin/env python3
"""Remove a registered OpenDock service and its service-owned resources."""

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from opendock_settings import CONFIG, initialize


ROOT = Path(__file__).resolve().parents[1]
SERVICES = ROOT / "services"
HERMES = SERVICES / "hermes"
COMPOSE = HERMES / "compose.yml"
SERVICE_CONFIG = ROOT / "services" / "hermes" / ".env"
SERVICE_CONFIG_EXAMPLE = ROOT / "services" / "hermes" / ".env.default"
LEGACY_ENV = ROOT / "common.env"
SANDBOX_DATA = HERMES / "data" / "sandboxes"
SANDBOX_IMAGE = "nousresearch/hermes-sandbox:desktop"
PROJECT = "hermes"


class RemovalError(Exception):
    pass


def run_command(args, *, capture=False, check=True):
    try:
        result = subprocess.run(
            [str(arg) for arg in args], cwd=ROOT, text=True,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None, check=False,
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
    for raw in path.read_text().splitlines():
        line = raw.strip()
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


def compose_prefix():
    directory = HERMES
    command = ["docker", "compose", "--project-directory", directory]
    for env_file in (
        CONFIG / "core.env.default", CONFIG / "core.env",
        CONFIG / "infra.env.default", CONFIG / "infra.env",
        CONFIG / "shared" / "mail.env.default", CONFIG / "shared" / "mail.env",
        SERVICE_CONFIG_EXAMPLE, LEGACY_ENV, HERMES / ".env",
    ):
        if env_file.is_file():
            command += ["--env-file", env_file]
    command += ["-f", COMPOSE, "-p", PROJECT]
    return command


def routes_for_removal(domains):
    if domains.DOMAINS_FILE.is_file():
        return domains.parse_domains_file()
    if CONFIG.joinpath("core.env").is_file() or LEGACY_ENV.is_file():
        return domains.default_routes()
    return []


def sandbox_container_ids(sandbox_root, compose_ids):
    raw_ids = run_command(
        ["docker", "ps", "-aq", "--filter", "label=hermes-task-id"], capture=True
    ).stdout.splitlines()
    candidates = [item.strip() for item in raw_ids if item.strip() and item.strip() not in compose_ids]
    if not candidates:
        return []
    inspected = json.loads(run_command(["docker", "inspect", *candidates], capture=True).stdout)
    root = sandbox_root.resolve()
    matched = []
    for container in inspected:
        for mount in container.get("Mounts", []):
            source = mount.get("Source")
            if not source:
                continue
            resolved = Path(source).resolve()
            try:
                resolved.relative_to(root)
            except ValueError:
                continue
            matched.append({
                "id": container.get("Id", ""),
                "name": container.get("Name", "").lstrip("/"),
                "image": container.get("Config", {}).get("Image", ""),
            })
            break
    return matched


def build_plan():
    os.environ.setdefault("HERMES_SANDBOX_DIR", str(SANDBOX_DATA))
    if not COMPOSE.is_file():
        raise RemovalError("Hermes is not installed in this OpenDock checkout.")
    domains = domains_module()
    if CONFIG.is_symlink() or SERVICE_CONFIG.parent.is_symlink():
        raise RemovalError("Refusing to inspect Hermes config through a symlink.")
    if SERVICE_CONFIG.is_symlink():
        raise RemovalError("Refusing to edit Hermes config because it is a symlink.")
    if LEGACY_ENV.is_symlink():
        raise RemovalError("Refusing to migrate legacy config through a symlink.")
    if domains.DOMAINS_FILE.is_symlink():
        raise RemovalError("Refusing to edit domains.conf because it is a symlink.")
    if SANDBOX_DATA.is_symlink():
        raise RemovalError(f"Refusing to remove sandbox data through a symlink: {SANDBOX_DATA}")
    resolved_sandbox = SANDBOX_DATA.resolve()
    try:
        resolved_sandbox.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise RemovalError(f"Sandbox data path escapes the repository: {SANDBOX_DATA}") from exc

    all_routes = routes_for_removal(domains)
    routes = [route for route in all_routes
              if route.get("type") == "docker" and route.get("target") == "hermes"]

    compose_ids = [item.strip() for item in run_command(
        ["docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={PROJECT}"],
        capture=True,
    ).stdout.splitlines() if item.strip()]
    sandbox_containers = sandbox_container_ids(SANDBOX_DATA, set(compose_ids))
    volumes = [item.strip() for item in run_command(
        ["docker", "volume", "ls", "--filter", f"label=com.docker.compose.project={PROJECT}",
         "--format", "{{.Name}}"], capture=True,
    ).stdout.splitlines() if item.strip()]
    images = [item.strip() for item in run_command(
        [*compose_prefix(), "config", "--images"], capture=True,
    ).stdout.splitlines() if item.strip()]
    if SANDBOX_IMAGE not in images:
        images.append(SANDBOX_IMAGE)

    service_values = parse_env(SERVICE_CONFIG)
    legacy_values = parse_env(LEGACY_ENV)
    service_keys = {key for key in parse_env(SERVICE_CONFIG_EXAMPLE) if key.startswith("HERMES_")}
    service_keys.update(key for key in service_values if key.startswith("HERMES_"))
    legacy_keys = {key for key in legacy_values if key.startswith("HERMES_")}
    configured_keys = sorted(service_keys & (service_values.keys() | legacy_values.keys()))

    return {
        "domains": domains,
        "routes": routes,
        "compose_ids": compose_ids,
        "sandbox_containers": sandbox_containers,
        "volumes": volumes,
        "images": images,
        "configured_keys": configured_keys,
        "remove_service_config": SERVICE_CONFIG.exists() or bool(legacy_keys),
        "migrate_legacy_config": LEGACY_ENV.is_file(),
        "remove_sandbox_data": SANDBOX_DATA.exists(),
    }


def print_plan(plan):
    print("Complete removal plan for hermes:")
    print("  Stop and remove Hermes Compose containers")
    if plan["compose_ids"]:
        print(f"    {len(plan['compose_ids'])} Compose container(s)")
    else:
        print("    (none currently present)")
    print("  Remove Hermes Docker sandbox containers:")
    if plan["sandbox_containers"]:
        for item in plan["sandbox_containers"]:
            print(f"    {item['name']} ({item['image']})")
    else:
        print("    (none using this Hermes sandbox directory)")
    print("  Remove Hermes Compose named volumes:")
    for volume in plan["volumes"] or ["(none currently present)"]:
        print(f"    {volume}")
    print("  Remove Hermes images if not in use by another container:")
    for image in plan["images"]:
        print(f"    {image}")
    print("  Remove Hermes public routes and Cloudflare Tunnel/DNS entries:")
    for route in plan["routes"] or [{"hostname": "(none configured)"}]:
        print(f"    {route['hostname']}")
    if not (ROOT / "cloudflare.env").is_file():
        print("    Cloudflare API cleanup unavailable; cloudflare.env is absent")
    if plan["remove_sandbox_data"]:
        print(f"  Delete sandbox workspace data: {SANDBOX_DATA.relative_to(ROOT)}/")
    print("  Remove Hermes settings from services/hermes/.env:")
    for key in plan["configured_keys"] or ["(none configured)"]:
        print(f"    {key}")
    if plan["remove_service_config"]:
        print("    A permission-restricted Hermes config backup will be retained.")
    if plan.get("migrate_legacy_config"):
        print("  Migrate remaining common.env values to their owner files and retain its backup.")
    print("  Preserve OpenDock code, core/shared settings, shared infra, and Caddy state.")


def backup_service_config():
    backup_dir = ROOT / "backups" / "config" / "services" / "hermes"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup = backup_dir / f".env.{timestamp}.bak"
    shutil.copy2(SERVICE_CONFIG, backup)
    backup.chmod(0o600)
    return backup


def remove_service_config():
    if not SERVICE_CONFIG.is_file():
        return
    backup_service_config()
    SERVICE_CONFIG.unlink()


def remove_routes(plan):
    if not plan["routes"]:
        return
    domains = plan["domains"]
    current = routes_for_removal(domains)
    current_routes = [route for route in current
                      if route.get("type") == "docker" and route.get("target") == "hermes"]
    if not current_routes:
        return
    for route in current_routes:
        run_command([sys.executable, ROOT / "scripts" / "publish-cloudflare.py",
                     "remove", route["hostname"]])
    remaining = [route for route in current if not (
        route.get("type") == "docker" and route.get("target") == "hermes")]
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


def remove_hermes(plan):
    # Migration is a change, so defer it until after the user confirms removal.
    initialize()
    # Withdraw public access before stopping the service.
    remove_routes(plan)

    run_command([*compose_prefix(), "down", "--volumes", "--remove-orphans"])

    sandbox_ids = [item["id"] for item in plan["sandbox_containers"] if item.get("id")]
    if sandbox_ids:
        run_command(["docker", "rm", "-f", *sandbox_ids])

    if SANDBOX_DATA.exists():
        shutil.rmtree(SANDBOX_DATA)
        print(f"Removed {SANDBOX_DATA.relative_to(ROOT)}/")

    remove_service_config()

    for image in plan["images"]:
        result = run_command(["docker", "image", "rm", image], capture=True, check=False)
        if result.returncode:
            detail = (result.stderr or result.stdout or "image is absent or in use").strip()
            print(f"Kept image {image}: {detail}")
        else:
            print(f"Removed image {image}")

    print("Hermes removal complete. Run './opendock launch hermes' to set it up again.")


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) not in (1, 2) or args[0] != "hermes" or (len(args) == 2 and args[1] != "--dry-run"):
        print("Removal is currently enabled for Hermes only.", file=sys.stderr)
        print("Usage: ./opendock remove hermes [--dry-run]", file=sys.stderr)
        return 2
    try:
        plan = build_plan()
        print_plan(plan)
        if len(args) == 2:
            print("Dry run: no changes made.")
            return 0
        if not sys.stdin.isatty():
            raise RemovalError("Removal requires an interactive confirmation; no changes were made.")
        print()
        print("This permanently deletes Hermes settings, conversations, sandbox data, "
              "and its configured public routes.")
        confirmation = input("Type REMOVE hermes to continue: ")
        if confirmation != "REMOVE hermes":
            print("Removal cancelled. No changes made.")
            return 0
        remove_hermes(plan)
    except (RemovalError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"OpenDock remove: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
