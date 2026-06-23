#!/usr/bin/env python3
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
TARGET = sys.argv[1] if len(sys.argv) > 1 else "all"
COMMON_ENV = ROOT_DIR / "common.env"
COMMON_ENV_EXAMPLE = ROOT_DIR / "common.env.example"
CLOUDFLARE_ENV = ROOT_DIR / "cloudflare.env"
ORIGIN_SERVICE_URL = os.environ.get("ORIGIN_SERVICE_URL", "http://localhost:80")
API_BASE = "https://api.cloudflare.com/client/v4"


def parse_env_file(path):
    values = {}
    if not path.exists():
        return values

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            continue

        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]

        values[key] = value

    return values


def service_env_key(service):
    return f"{service.replace('-', '_').upper()}_SUBDOMAIN"


def service_subdomain(env, service):
    return env.get(service_env_key(service)) or service


def service_is_publishable(service):
    return (
        (ROOT_DIR / "services" / service / "compose.yml").is_file()
        and (ROOT_DIR / "gateway" / "caddy" / "conf.d" / f"{service}.caddy").is_file()
    )


def all_publishable_services():
    services_dir = ROOT_DIR / "services"
    if not services_dir.is_dir():
        return []

    services = []
    for compose in services_dir.glob("*/compose.yml"):
        service = compose.parent.name
        if service_is_publishable(service):
            services.append(service)

    return sorted(services)


def target_services(target):
    if target in ("all", "services"):
        return all_publishable_services()

    if target in ("infra", "gateway"):
        return []

    compose = ROOT_DIR / "services" / target / "compose.yml"
    if not compose.is_file():
        raise SystemExit(f"Unknown service target: {target}")

    return [target] if service_is_publishable(target) else []


def load_env():
    if not COMMON_ENV.exists():
        raise SystemExit(
            "Missing required file: common.env\n\n"
            "To continue:\n"
            "  cp common.env.example common.env\n"
            "  nano common.env\n"
            "  make check-config"
        )

    env = {}
    env.update(parse_env_file(COMMON_ENV_EXAMPLE))
    env.update(parse_env_file(COMMON_ENV))
    env.update(os.environ)
    return env


def build_routes(env, services):
    stack_domain = env.get("STACK_DOMAIN", "").strip()
    if not stack_domain:
        raise SystemExit("Missing STACK_DOMAIN in common.env")

    routes = []
    for service in services:
        subdomain = service_subdomain(env, service).strip()
        if not subdomain:
            continue
        routes.append(
            {
                "service": service,
                "subdomain": subdomain,
                "hostname": f"{subdomain}.{stack_domain}",
                "origin": ORIGIN_SERVICE_URL,
            }
        )

    return stack_domain, routes


def print_publish_plan(stack_domain, routes):
    print(f"Publish target: {TARGET}")
    print(f"Stack domain: {stack_domain}")
    print()

    if not routes:
        print(f"No publishable services for target: {TARGET}")
        return

    print("Public routes:")
    for route in routes:
        print(f"  {route['hostname']:<28} -> {route['origin']}")


class CloudflareClient:
    def __init__(self, token):
        self.token = token

    def request(self, method, path, payload=None, query=None):
        url = f"{API_BASE}{path}"
        if query:
            url = f"{url}?{urllib.parse.urlencode(query)}"

        body = None
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

        if payload is not None:
            body = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(url, data=body, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                data = response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            data = error.read().decode("utf-8")
            raise RuntimeError(f"Cloudflare API {method} {path} failed: {data}") from error

        parsed = json.loads(data)
        if not parsed.get("success", False):
            raise RuntimeError(f"Cloudflare API {method} {path} failed: {data}")

        return parsed.get("result")


def required_cloudflare_env(env):
    names = [
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_TUNNEL_ID",
    ]
    missing = [name for name in names if not env.get(name)]
    if missing:
        raise SystemExit(f"cloudflare.env is present but missing: {' '.join(missing)}")


def lookup_zone(client, stack_domain):
    zones = client.request("GET", "/zones", query={"name": stack_domain}) or []
    exact_matches = [zone for zone in zones if zone.get("name") == stack_domain]

    if not exact_matches:
        raise SystemExit(
            f"Could not find Cloudflare zone for STACK_DOMAIN={stack_domain}. "
            "Make sure the domain is added to Cloudflare and the token can read zones."
        )

    if len(exact_matches) > 1:
        raise SystemExit(
            f"Found multiple Cloudflare zones for STACK_DOMAIN={stack_domain}. "
            "This is unexpected; narrow the token scope or check the account."
        )

    zone = exact_matches[0]
    account = zone.get("account") or {}
    account_id = account.get("id")
    zone_id = zone.get("id")

    if not zone_id or not account_id:
        raise SystemExit(
            "Cloudflare zone lookup succeeded but did not return zone/account IDs."
        )

    return {
        "zone_id": zone_id,
        "account_id": account_id,
        "zone_name": zone.get("name"),
        "account_name": account.get("name"),
    }


def split_ingress_rules(ingress):
    hostname_rules = []
    fallback_rules = []

    for rule in ingress:
        if rule.get("hostname"):
            hostname_rules.append(rule)
        else:
            fallback_rules.append(rule)

    return hostname_rules, fallback_rules


def sync_tunnel(client, account_id, env, routes):
    tunnel_id = env["CLOUDFLARE_TUNNEL_ID"]
    path = f"/accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations"

    result = client.request("GET", path) or {}
    config = dict(result.get("config") or {})
    ingress = list(config.get("ingress") or [])
    hostname_rules, fallback_rules = split_ingress_rules(ingress)

    if not fallback_rules:
        fallback_rules = [{"service": "http_status:404"}]

    by_hostname = {rule.get("hostname"): rule for rule in hostname_rules}
    changed = False
    statuses = []

    for route in routes:
        hostname = route["hostname"]
        existing = by_hostname.get(hostname)
        if existing:
            if existing.get("service") == route["origin"]:
                statuses.append((hostname, "exists"))
            else:
                existing["service"] = route["origin"]
                statuses.append((hostname, "updated"))
                changed = True
        else:
            rule = {"hostname": hostname, "service": route["origin"]}
            hostname_rules.append(rule)
            by_hostname[hostname] = rule
            statuses.append((hostname, "added"))
            changed = True

    if changed:
        config["ingress"] = hostname_rules + fallback_rules
        client.request("PUT", path, {"config": config})

    return statuses


def sync_dns(client, zone_id, env, routes):
    tunnel_id = env["CLOUDFLARE_TUNNEL_ID"]
    tunnel_target = f"{tunnel_id}.cfargotunnel.com"
    statuses = []

    for route in routes:
        hostname = route["hostname"]
        records = client.request(
            "GET",
            f"/zones/{zone_id}/dns_records",
            query={"name": hostname},
        ) or []

        if records:
            matching = [
                record
                for record in records
                if record.get("type") == "CNAME" and record.get("content") == tunnel_target
            ]
            if matching:
                statuses.append((hostname, "exists"))
                continue

            summary = ", ".join(
                f"{record.get('type')} {record.get('content')}" for record in records
            )
            statuses.append((hostname, f"conflict ({summary})"))
            continue

        client.request(
            "POST",
            f"/zones/{zone_id}/dns_records",
            {
                "type": "CNAME",
                "name": hostname,
                "content": tunnel_target,
                "ttl": 1,
                "proxied": True,
            },
        )
        statuses.append((hostname, "created"))

    return statuses


def print_statuses(title, statuses):
    print(title)
    if not statuses:
        print("  (none)")
        return

    for hostname, status in statuses:
        print(f"  {hostname:<28} {status}")


def main():
    env = load_env()
    services = target_services(TARGET)
    stack_domain, routes = build_routes(env, services)
    print_publish_plan(stack_domain, routes)

    if not CLOUDFLARE_ENV.exists():
        print()
        print("cloudflare.env not found. Skipping Cloudflare API sync.")
        print("Copy cloudflare.env.example to cloudflare.env to enable automatic publishing.")
        return

    cf_env = {}
    cf_env.update(env)
    cf_env.update(parse_env_file(CLOUDFLARE_ENV))

    if stack_domain == "example.com":
        raise SystemExit(
            "\nRefusing to sync Cloudflare with STACK_DOMAIN=example.com.\n"
            "Set your real domain in common.env first."
        )

    required_cloudflare_env(cf_env)

    if not routes:
        print()
        print("No Cloudflare changes needed.")
        return

    client = CloudflareClient(cf_env["CLOUDFLARE_API_TOKEN"])

    print()
    print("Syncing Cloudflare...")
    zone = lookup_zone(client, stack_domain)
    print(f"Cloudflare zone: {zone['zone_name']}")

    tunnel_statuses = sync_tunnel(client, zone["account_id"], cf_env, routes)
    dns_statuses = sync_dns(client, zone["zone_id"], cf_env, routes)

    print()
    print_statuses("Tunnel routes:", tunnel_statuses)
    print()
    print_statuses("DNS records:", dns_statuses)

    conflicts = [status for _, status in dns_statuses if status.startswith("conflict")]
    if conflicts:
        raise SystemExit(
            "\nSome DNS records already exist with different values. "
            "Review them in Cloudflare before rerunning publish."
        )

    print()
    print("Open:")
    for route in routes:
        print(f"  https://{route['hostname']}")


if __name__ == "__main__":
    main()
