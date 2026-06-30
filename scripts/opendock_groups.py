from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
GROUPS_FILE = ROOT_DIR / "services" / "groups.conf"


def service_targets():
    services_dir = ROOT_DIR / "services"
    if not services_dir.is_dir():
        return []
    return sorted(compose.parent.name for compose in services_dir.glob("*/compose.yml"))


def is_service(target):
    return (ROOT_DIR / "services" / target / "compose.yml").is_file()


def groups():
    parsed = {}
    if not GROUPS_FILE.is_file():
        return parsed

    for raw_line in GROUPS_FILE.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        name, services = line.split(":", 1)
        name = name.strip()
        members = services.split()
        if name and members:
            parsed[name] = members

    return parsed


def group_services(target):
    if is_service(target):
        return []
    return groups().get(target, [])


def validate_services(services):
    missing = [service for service in services if not is_service(service)]
    if missing:
        raise SystemExit(f"Unknown service in services/groups.conf: {' '.join(missing)}")
