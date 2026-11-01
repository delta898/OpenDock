#!/usr/bin/env python3
"""Resolve OpenDock hostnames to Docker services or static web roots."""
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

from opendock_settings import load_values


ROOT = Path(__file__).resolve().parents[1]
DOMAINS_FILE = ROOT / "domains.conf"
GENERATED_ROUTES = ROOT / "gateway" / "caddy" / "conf.d" / "zz-opendock-routes.caddy"
STATIC_ROOT = ROOT / "static-sites"
HOST_RE = re.compile(
    r"(?=.{1,253}$)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)"
    r"(?:\.(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?))*\.?$"
)
TARGET_RE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,62}")


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


def service_routes(env):
    domain = env.get("STACK_DOMAIN", "").strip()
    if not domain:
        raise SystemExit("Missing STACK_DOMAIN. Run './opendock setup' to configure the core domain.")
    routes = []
    for compose in sorted((ROOT / "services").glob("*/compose.yml")):
        service = compose.parent.name
        if not (ROOT / "gateway" / "caddy" / "conf.d" / f"{service}.caddy").is_file():
            continue
        key = f"{service.replace('-', '_').upper()}_SUBDOMAIN"
        subdomain = env.get(key) or service
        routes.append({"hostname": f"{subdomain}.{domain}", "type": "docker", "target": service})
    return routes


def parse_domains_file():
    routes = []
    for line_number, raw in enumerate(DOMAINS_FILE.read_text().splitlines(), 1):
        line = raw.partition("#")[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 3:
            raise SystemExit(
                f"domains.conf:{line_number}: expected <hostname> <docker|static> <target>"
            )
        hostname, route_type, target = parts
        if not HOST_RE.fullmatch(hostname):
            raise SystemExit(f"domains.conf:{line_number}: invalid hostname: {hostname}")
        if route_type not in {"docker", "static"}:
            raise SystemExit(f"domains.conf:{line_number}: type must be docker or static")
        if route_type == "docker" and not TARGET_RE.fullmatch(target):
            raise SystemExit(f"domains.conf:{line_number}: invalid Docker service name: {target}")
        if route_type == "static" and target != hostname.rstrip(".").lower():
            raise SystemExit(
                f"domains.conf:{line_number}: static web root must match its hostname"
            )
        routes.append(
            {"hostname": hostname.rstrip(".").lower(), "type": route_type, "target": target}
        )
    return routes


def resolve_routes():
    env = load_values(process_env=False)
    routes = parse_domains_file() if DOMAINS_FILE.exists() else service_routes(env)
    validate_routes(routes)
    return routes


def validate_routes(routes):
    seen = {}
    for route in routes:
        hostname = route["hostname"].lower()
        if not HOST_RE.fullmatch(hostname):
            raise SystemExit(f"Invalid hostname in domain routes: {route['hostname']}")
        if hostname in seen:
            raise SystemExit(f"Duplicate hostname {route['hostname']} in domain routes")
        seen[hostname] = route
        if route["type"] == "docker":
            if not (ROOT / "services" / route["target"] / "compose.yml").is_file():
                raise SystemExit(f"Unknown Docker service in domain routes: {route['target']}")
            if not (ROOT / "gateway" / "caddy" / "conf.d" / f"{route['target']}.caddy").is_file():
                raise SystemExit(f"Missing Caddy service route: {route['target']}")
        else:
            if route["target"] != hostname.rstrip("."):
                raise SystemExit(f"Static web root must match hostname: {hostname}")
            web_root = (STATIC_ROOT / route["target"]).resolve()
            try:
                web_root.relative_to(STATIC_ROOT.absolute())
            except ValueError:
                raise SystemExit(f"Static web root escapes static-sites/: {route['target']}")
            if not web_root.is_dir():
                raise SystemExit(
                    f"Missing static web root static-sites/{route['target']}; create it before publishing"
                )


def default_routes():
    env = load_values(process_env=False)
    return service_routes(env)


def save_routes(routes):
    if DOMAINS_FILE.exists():
        backup_dir = ROOT / "backups" / "domain-routes"
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(DOMAINS_FILE, backup_dir / f"domains.conf.{timestamp}.bak")
    rows = [
        "# One hostname per route. Docker targets are services/*; static targets are static-sites/*.",
        "# Format: <hostname> <docker|static> <target>",
    ]
    rows.extend(
        f"{route['hostname']} {route['type']} {route['target']}" for route in routes
    )
    DOMAINS_FILE.write_text("\n".join(rows) + "\n")
    os.chmod(DOMAINS_FILE, 0o600)


def ensure_domains_file():
    if not DOMAINS_FILE.exists():
        routes = default_routes()
        validate_routes(routes)
        save_routes(routes)
    return parse_domains_file()


def parse_target(hostname, value):
    if value == "static":
        return "static", hostname
    if value.startswith("static:"):
        raise SystemExit("Static web roots are derived from the hostname; use 'static'.")
    if not TARGET_RE.fullmatch(value):
        raise SystemExit("Target must be a known OpenDock service name or 'static'.")
    return "docker", value


def add_route(hostname, target_value, routes=None):
    hostname = hostname.rstrip(".").lower()
    if not HOST_RE.fullmatch(hostname):
        raise SystemExit(f"Invalid hostname: {hostname}")
    route_type, target = parse_target(hostname, target_value)
    candidate = {"hostname": hostname, "type": route_type, "target": target}
    routes = ensure_domains_file() if routes is None else routes
    existing = next((route for route in routes if route["hostname"].lower() == hostname), None)
    if existing:
        raise SystemExit(
            f"{hostname} is already mapped to {existing['type']}:{existing['target']}."
        )
    updated = routes + [candidate]
    if route_type == "static":
        (STATIC_ROOT / hostname).mkdir(parents=True, exist_ok=True)
    validate_routes(updated)
    save_routes(updated)
    print(f"Added {hostname} -> {route_type}:{target}")
    if route_type == "static":
        print(f"Web root: {STATIC_ROOT / hostname}/")
        print("Place the site's files there, then run:")
        print(f"  ./opendock launch {hostname}")
    else:
        print(f"Apply the route with: ./opendock launch {hostname}")


def remove_route(hostname):
    hostname = hostname.rstrip(".").lower()
    routes = ensure_domains_file()
    updated = [route for route in routes if route["hostname"].lower() != hostname]
    if len(updated) == len(routes):
        raise SystemExit(f"No OpenDock route is configured for {hostname}.")
    save_routes(updated)
    print(f"Removed OpenDock's local route for {hostname}.")
    print("Static files are preserved.")


def render_routes(routes):
    lines = ["# Generated by OpenDock from its domain map. Do not edit.", ""]
    for route in routes:
        hostname = route["hostname"]
        if route["type"] == "docker":
            handler = f"import {route['target'].replace('-', '_')}_proxy"
        else:
            handler = "\n".join(
                [
                    "import security_headers",
                    f"root * /srv/static-sites/{route['target']}",
                    "encode zstd gzip",
                    "file_server {\n    hide .git .env\n}",
                ]
            )
        for scheme in ("http", "https"):
            indented_handler = "\n".join(f"    {line}" for line in handler.splitlines())
            lines.extend([f"{scheme}://{hostname} {{", indented_handler, "}", ""])
    GENERATED_ROUTES.write_text("\n".join(lines))


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else "list"
    if command == "add" and len(sys.argv) == 4:
        add_route(sys.argv[2], sys.argv[3])
        return
    if command == "remove" and len(sys.argv) == 3:
        remove_route(sys.argv[2])
        return
    if command == "lookup" and len(sys.argv) == 3:
        hostname = sys.argv[2].rstrip(".").lower()
        route = next((route for route in resolve_routes() if route["hostname"] == hostname), None)
        if route:
            print(f"{route['type']}:{route['target']}")
        return
    if command == "legacy-check" and len(sys.argv) == 3:
        service = sys.argv[2]
        hostnames = [route["hostname"] for route in resolve_routes()
                     if route["type"] == "docker" and route["target"] == service]
        if len(hostnames) > 1:
            print(f"'{service}' has multiple hostnames; use './opendock launch <hostname>':")
            for hostname in hostnames:
                print(f"  ./opendock launch {hostname}")
            raise SystemExit(2)
        return
    routes = resolve_routes()
    if command == "render":
        render_routes(routes)
        return
    if command == "list":
        hostname_filter = sys.argv[2].lower() if len(sys.argv) > 2 else None
        if hostname_filter:
            routes = [route for route in routes if route["hostname"].lower() == hostname_filter]
        for route in routes:
            print(f"{route['hostname']:<36} {route['type']}:{route['target']}")
        return
    raise SystemExit("Usage: opendock-domains.py [list [hostname]|add <hostname> <service|static>|remove <hostname>|lookup <hostname>|render]")


if __name__ == "__main__":
    main()
