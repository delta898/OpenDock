#!/usr/bin/env python3
"""Resolve OpenDock hostnames to static, service, or external upstream targets."""
import ipaddress
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from opendock_root import resolve_root
from opendock_settings import load_values
from opendock_catalog import ServiceCatalog


ROOT = resolve_root(__file__)
DOMAINS_FILE = ROOT / "domains.conf"
GENERATED_ROUTES = ROOT / "gateway" / "caddy" / "conf.d" / "zz-opendock-routes.caddy"
GENERATED_HANDLERS = ROOT / "gateway" / "caddy" / "conf.d" / "yy-opendock-service-handlers.caddy"
STATIC_ROOT = ROOT / "static-sites"
HOST_RE = re.compile(
    r"(?=.{1,253}$)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)"
    r"(?:\.(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?))*\.?$"
)
TARGET_RE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,62}")
ROUTE_TYPES = {"static", "service", "external"}


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
    catalog = ServiceCatalog(ROOT)
    for service in catalog.services:
        routing = service.routing
        if not routing:
            continue
        subdomain = env.get(routing["subdomain_key"]) or service.name
        routes.append({
            "hostname": f"{subdomain}.{domain}",
            "type": "service",
            "target": service.name,
        })
    return routes


def parse_domains_file():
    routes = []
    for line_number, raw in enumerate(DOMAINS_FILE.read_text().splitlines(), 1):
        line = raw.partition("#")[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            raise SystemExit(
                f"domains.conf:{line_number}: expected <type> <hostname> [<target>]"
            )
        if parts[0] in ROUTE_TYPES:
            route_type, hostname = parts[:2]
            expected_parts = 2 if route_type == "static" else 3
            if len(parts) != expected_parts:
                suffix = "" if route_type == "static" else " <target>"
                raise SystemExit(
                    f"domains.conf:{line_number}: expected {route_type} <hostname>{suffix}"
                )
            target = hostname.rstrip(".").lower() if route_type == "static" else parts[2]
        elif len(parts) == 3 and parts[1] in {"docker", "service", "static", "external"}:
            # Accept the previous hostname-first file layout and normalize it on write.
            hostname, stored_type, target = parts
            route_type = "service" if stored_type == "docker" else stored_type
        else:
            raise SystemExit(
                f"domains.conf:{line_number}: expected <type> <hostname> [<target>]"
            )
        if route_type not in ROUTE_TYPES:
            raise SystemExit(
                f"domains.conf:{line_number}: type must be static, service, or external"
            )
        if route_type == "static":
            target = hostname.rstrip(".").lower()
        if not HOST_RE.fullmatch(hostname):
            raise SystemExit(f"domains.conf:{line_number}: invalid hostname: {hostname}")
        if route_type == "service" and not TARGET_RE.fullmatch(target):
            raise SystemExit(f"domains.conf:{line_number}: invalid service ID: {target}")
        if route_type == "external":
            validate_external_target(target, line_number=line_number)
        routes.append(
            {"hostname": hostname.rstrip(".").lower(), "type": route_type, "target": target}
        )
    return routes


def resolve_routes():
    env = load_values(process_env=False)
    routes = parse_domains_file() if DOMAINS_FILE.exists() else service_routes(env)
    local_hostname = os.environ.get("OPENDOCK_LOCAL_TEST_HOSTNAME", "").strip().lower()
    if os.environ.get("OPENDOCK_LOCAL_TEST") == "1" and local_hostname:
        routes = [route for route in routes if route["hostname"] != local_hostname]
        service_id = os.environ.get("OPENDOCK_LOCAL_TEST_SERVICE", "").strip()
        if not service_id:
            session_file = ROOT / "config" / "local-test" / "session.json"
            try:
                import json
                service_id = json.loads(session_file.read_text()).get("service_id", "")
            except (OSError, ValueError):
                service_id = ""
        if service_id:
            routes.append({"hostname": local_hostname, "type": "service", "target": service_id})
    validate_routes(routes)
    return routes


def validate_routes(routes):
    seen = {}
    catalog = ServiceCatalog(ROOT)
    for route in routes:
        hostname = route["hostname"].lower()
        if not HOST_RE.fullmatch(hostname):
            raise SystemExit(f"Invalid hostname in domain routes: {route['hostname']}")
        if hostname in seen:
            raise SystemExit(f"Duplicate hostname {route['hostname']} in domain routes")
        seen[hostname] = route
        if route["type"] == "service":
            try:
                service = catalog.get(route["target"])
            except ValueError as error:
                raise SystemExit(f"Unknown service in domain routes: {route['target']}") from error
            handler = service.routing.get("caddy_handler")
            if not handler:
                raise SystemExit(
                    f"Service {service.name} does not declare public routing metadata."
                )
            handler_file = catalog.routing_file(service)
            if handler_file is None or not handler_file.is_file() or f"({handler})" not in handler_file.read_text():
                raise SystemExit(f"Missing Caddy handler {handler} for service {service.name}.")
        elif route["type"] == "static":
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
        elif route["type"] == "external":
            validate_external_target(route["target"])
        else:
            raise SystemExit(f"Unsupported route type: {route['type']}")


def default_routes():
    env = load_values(process_env=False)
    return service_routes(env)


def save_routes(routes):
    if os.environ.get("OPENDOCK_LOCAL_TEST") == "1" and any(
        route["type"] == "external" for route in routes
    ):
        raise SystemExit("External routes are not allowed in local test mode.")
    if DOMAINS_FILE.exists():
        backup_dir = ROOT / "backups" / "domain-routes"
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(DOMAINS_FILE, backup_dir / f"domains.conf.{timestamp}.bak")
    rows = [
        "# One route per line. Service targets are installed OpenDock services.",
        "# Format: <type> <hostname> [<target>]",
        "# Examples: static docs.example.org | service app.example.org n8n-v3 | external ai.example.org http://host.docker.internal:1234",
    ]
    for route in routes:
        if route["type"] == "static":
            rows.append(f"static {route['hostname']}")
        else:
            rows.append(f"{route['type']} {route['hostname']} {route['target']}")
    DOMAINS_FILE.write_text("\n".join(rows) + "\n")
    os.chmod(DOMAINS_FILE, 0o600)


def ensure_domains_file():
    if not DOMAINS_FILE.exists():
        routes = default_routes()
        validate_routes(routes)
        save_routes(routes)
    return parse_domains_file()


def add_missing_default_routes(service_names):
    """Add defaults for selected services in one validated domains.conf write."""
    if not DOMAINS_FILE.exists():
        return []  # The implicit default route set already covers all installed packages.
    routes = parse_domains_file()
    defaults = {
        route["target"]: route
        for route in default_routes()
        if route["type"] == "service"
    }
    present = {
        route["target"] for route in routes if route["type"] == "service"
    }
    added = []
    for service in service_names:
        if service in present or service not in defaults:
            continue
        routes.append(defaults[service])
        present.add(service)
        added.append(defaults[service]["hostname"])
    if added:
        validate_routes(routes)
        save_routes(routes)
    return added


def validate_external_target(value, *, line_number=None):
    prefix = f"domains.conf:{line_number}: " if line_number else ""

    def invalid(reason):
        raise SystemExit(
            f"{prefix}invalid external upstream URL ({reason}); use an http:// or https:// origin "
            "without credentials, path, query, or fragment"
        )

    if (not isinstance(value, str) or not value
            or any(ord(char) < 33 or ord(char) == 127 for char in value)):
        invalid("whitespace or control character")
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as error:
        invalid(str(error))
    if parsed.scheme not in {"http", "https"}:
        invalid("scheme must be http or https")
    if not hostname or parsed.username is not None or parsed.password is not None:
        invalid("host is missing or credentials are present")
    if parsed.netloc.endswith(":"):
        invalid("port is empty")
    if (parsed.path not in {"", "/"} or parsed.query or parsed.fragment
            or "?" in value or "#" in value):
        invalid("only an origin URL is supported")
    if port is not None and not 1 <= port <= 65535:
        invalid("port is outside 1-65535")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        if not HOST_RE.fullmatch(hostname) or "%" in hostname:
            invalid("invalid hostname or IP address")
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def parse_target(route_type, hostname, value=None):
    if route_type == "static":
        if value is not None:
            raise SystemExit(
                "Static routes do not take a target; their web root is derived from the hostname."
            )
        return hostname
    if route_type == "service":
        if not value:
            raise SystemExit("Service routes require a service ID target.")
        if not TARGET_RE.fullmatch(value):
            raise SystemExit("Service target must be an installed OpenDock service ID.")
        return value
    if route_type == "external":
        if not value:
            raise SystemExit("External routes require an upstream URL target.")
        normalized = validate_external_target(value)
        return normalized
    raise SystemExit("Route type must be static, service, or external.")


def add_route(route_type, hostname, target_value=None, routes=None):
    hostname = hostname.rstrip(".").lower()
    if not HOST_RE.fullmatch(hostname):
        raise SystemExit(f"Invalid hostname: {hostname}")
    target = parse_target(route_type, hostname, target_value)
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
    suffix = "" if route_type == "static" else f":{target}"
    print(f"Added {hostname} -> {route_type}{suffix}")
    if route_type == "static":
        print(f"Web root: {STATIC_ROOT / hostname}/")
        print("Place the site's files there, then run:")
        print(f"  ./opendock launch {hostname}")
    elif route_type == "external":
        print("The upstream must be reachable from the Caddy container.")
        print(f"Apply the route with: ./opendock launch {hostname}")
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
    print("Static files are preserved; external upstreams are not stopped.")


def render_routes(routes):
    lines = ["# Generated by OpenDock from its domain map. Do not edit.", ""]
    handler_imports = ["# Generated by OpenDock from installed service packages. Do not edit.", ""]
    imported_handlers = set()
    catalog = ServiceCatalog(ROOT)
    for route in routes:
        hostname = route["hostname"]
        if route["type"] == "service":
            service = catalog.get(route["target"])
            handler_path = catalog.routing_file(service)
            if catalog.is_extension(service.name):
                relative = handler_path.relative_to(service.directory).as_posix()
                active_release = service.directory.relative_to(
                    ROOT / "services" / "extensions"
                ).as_posix()
                handler_file = f"/etc/opendock/extensions/{active_release}/{relative}"
                if handler_file not in imported_handlers:
                    handler_imports.append(f"import {handler_file}")
                    imported_handlers.add(handler_file)
                handler = f"import {service.routing['caddy_handler']}"
            else:
                handler = f"import {service.routing['caddy_handler']}"
        elif route["type"] == "static":
            handler = "\n".join(
                [
                    "import security_headers",
                    f"root * /srv/static-sites/{route['target']}",
                    "encode zstd gzip",
                    "file_server {\n    hide .git .env\n}",
                ]
            )
        else:
            upstream = validate_external_target(route["target"])
            handler = "\n".join(
                [
                    "import common_proxy",
                    "import security_headers",
                    f"reverse_proxy {upstream}",
                ]
            )
        indented_handler = "\n".join(f"    {line}" for line in handler.splitlines())
        # Cloudflare Tunnel terminates public TLS and connects to Caddy over HTTP.
        # An explicit HTTPS site makes Caddy attempt its own ACME certificate flow,
        # which cannot complete through the default tunnel-origin setup.
        lines.extend([f"http://{hostname} {{", indented_handler, "}", ""])
    GENERATED_HANDLERS.write_text("\n".join(handler_imports) + "\n")
    GENERATED_ROUTES.write_text("\n".join(lines))


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else "list"
    if command == "add-defaults" and len(sys.argv) >= 3:
        added = add_missing_default_routes(sys.argv[2:])
        for hostname in added:
            print(f"Added default hostname {hostname}")
        return
    if command == "add" and len(sys.argv) in {4, 5}:
        add_route(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) == 5 else None)
        return
    if command == "remove" and len(sys.argv) == 3:
        remove_route(sys.argv[2])
        return
    if command == "lookup" and len(sys.argv) == 3:
        hostname = sys.argv[2].rstrip(".").lower()
        route = next((route for route in resolve_routes() if route["hostname"] == hostname), None)
        if route:
            suffix = "" if route["type"] == "static" else f":{route['target']}"
            print(f"{route['type']}{suffix}")
        return
    if command == "legacy-check" and len(sys.argv) == 3:
        service = sys.argv[2]
        hostnames = [route["hostname"] for route in resolve_routes()
                     if route["type"] == "service" and route["target"] == service]
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
            target = "" if route["type"] == "static" else f" {route['target']}"
            print(f"{route['hostname']:<36} {route['type']}{target}")
        return
    raise SystemExit("Usage: opendock-domains.py [list [hostname]|add <type> <hostname> [<target>]|remove <hostname>|lookup <hostname>|render]")


if __name__ == "__main__":
    main()
