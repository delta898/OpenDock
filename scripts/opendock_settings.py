#!/usr/bin/env python3
"""Load, migrate, and update OpenDock's layered environment configuration."""

import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config"
LEGACY_ENV = ROOT / "common.env"
BACKUPS = ROOT / "backups" / "config"
BACKUPS_CREATED = []

SERVICE_NAMES = (
    "wordpress", "nextcloud", "immich", "jellyfin", "mastodon",
    "mattermost", "n8n", "uptime-kuma", "homepage", "supabase", "hermes",
)
SERVICE_PREFIXES = {
    service: service.replace("-", "_").upper() + "_"
    for service in SERVICE_NAMES
}
INFRA_KEYS = {"MARIADB_ROOT_PASSWORD", "POSTGRES_ADMIN_USER", "POSTGRES_ADMIN_PASSWORD"}
MAIL_PREFIX = "SMTP_"


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


def owner_path(key):
    if key == "STACK_DOMAIN":
        return Path("config") / "core.env"
    if key in INFRA_KEYS:
        return Path("config") / "infra.env"
    if key.startswith(MAIL_PREFIX):
        return Path("config") / "shared" / "mail.env"
    for service, prefix in SERVICE_PREFIXES.items():
        if key.startswith(prefix):
            if service == "hermes":
                return Path("services") / service / ".env"
            return Path("config") / "services" / f"{service}.env"
    raise ValueError(f"No configuration owner is registered for key: {key}")


def config_paths(service=None, examples=False):
    if examples:
        relative = [
            Path("core.env.default"), Path("infra.env.default"),
            Path("shared") / "mail.env.default",
        ]
    else:
        relative = [
            Path("core.env"), Path("infra.env"), Path("shared") / "mail.env",
        ]
    selected = SERVICE_NAMES if service is None else (service,)
    for name in selected:
        if name not in SERVICE_PREFIXES or name == "hermes":
            continue
        suffix = ".env.example" if examples else ".env"
        relative.append(Path("services") / f"{name}{suffix}")
    return [CONFIG / path for path in relative]


def load_values(service=None, *, examples=False, process_env=False, legacy=True):
    values = {}
    # Examples provide defaults; local values override them.
    for path in config_paths(service, examples=True):
        values.update(parse_env(path))
    if service in (None, "hermes"):
        values.update(parse_env(ROOT / "services" / "hermes" / ".env.default"))
    if examples:
        return values
    if legacy and LEGACY_ENV.is_file():
        values.update(parse_env(LEGACY_ENV))
    for path in config_paths(service):
        values.update(parse_env(path))
    if service:
        service_local = ROOT / "services" / service / ".env"
        values.update(parse_env(service_local))
    elif service is None:
        values.update(parse_env(ROOT / "services" / "hermes" / ".env"))
    if process_env:
        values.update(os.environ)
    return values


def compose_env_files(service=None):
    base = [
        CONFIG / "core.env.default", CONFIG / "core.env",
        CONFIG / "infra.env.default", CONFIG / "infra.env",
        CONFIG / "shared" / "mail.env.default", CONFIG / "shared" / "mail.env",
    ]
    if service == "hermes":
        base.append(ROOT / "services/hermes/.env.default")
    elif service in SERVICE_PREFIXES:
        base.extend((
            CONFIG / "services" / f"{service}.env.example",
            CONFIG / "services" / f"{service}.env",
        ))
    files = [path for path in base if path.is_file()]
    # Read-only compatibility for commands run before first setup/migration.
    if LEGACY_ENV.is_file():
        files.append(LEGACY_ENV)
    if service:
        local = ROOT / "services" / service / ".env"
        if local.is_file():
            files.append(local)
    return files


def _write_values(path, updates):
    if path.is_symlink():
        raise ValueError(f"Refusing to update config through a symlink: {path}")
    try:
        path.parent.resolve().relative_to(ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"Refusing to write outside the repository: {path}") from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text().splitlines() if path.is_file() else []
    changed = []
    seen = set()
    output = []
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
            output.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key not in updates:
            output.append(line)
            continue
        seen.add(key)
        if line.split("=", 1)[1].strip().strip("\"'") != str(updates[key]):
            output.append(f"{key}={updates[key]}")
            changed.append(key)
        else:
            output.append(line)
    for key in sorted(set(updates) - seen):
        if output and output[-1].strip():
            output.append("")
        output.append(f"{key}={updates[key]}")
        changed.append(key)
    if not changed:
        return []
    if path.is_file():
        relative = path.relative_to(ROOT)
        if relative.parts[0] == "config":
            relative = relative.relative_to("config")
        backup = BACKUPS / relative.parent / f"{relative.name}.{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.bak"
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup)
        backup.chmod(0o600)
        BACKUPS_CREATED.append(backup)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            stream.write("\n".join(output).rstrip() + "\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return changed


def write_values(updates):
    BACKUPS_CREATED.clear()
    by_path = {}
    for key, value in updates.items():
        by_path.setdefault(owner_path(key), {})[key] = value
    changed = []
    for relative, values in by_path.items():
        changed.extend(_write_values(ROOT / relative, values))
    return changed


def initialize():
    """Prepare config directories and migrate common.env exactly once."""
    if CONFIG.is_symlink():
        raise ValueError(f"Refusing to initialize config through a symlink: {CONFIG}")
    CONFIG.mkdir(parents=True, exist_ok=True)
    for directory in (CONFIG / "shared", CONFIG / "services"):
        if directory.is_symlink():
            raise ValueError(f"Refusing to initialize config through a symlink: {directory}")
    for path in config_paths():
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_symlink():
            raise ValueError(f"Refusing to initialize config through a symlink: {path}")
    hermes_local = ROOT / "services/hermes/.env"
    if hermes_local.is_symlink():
        raise ValueError(f"Refusing to initialize config through a symlink: {hermes_local}")

    if LEGACY_ENV.is_symlink():
        raise ValueError(f"Refusing to migrate legacy config through a symlink: {LEGACY_ENV}")
    if not LEGACY_ENV.is_file():
        return []

    legacy = parse_env(LEGACY_ENV)
    grouped = {}
    for key, value in legacy.items():
        grouped.setdefault(owner_path(key), {})[key] = value

    # Legacy values win over example placeholders but never overwrite an
    # already-created split setting. This makes a partially migrated install safe.
    migrated = []
    for relative, values in grouped.items():
        destination = ROOT / relative
        current = parse_env(destination)
        pending = {key: value for key, value in values.items() if key not in current}
        migrated.extend(_write_values(destination, pending))

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    BACKUPS.mkdir(parents=True, exist_ok=True)
    backup = BACKUPS / f"common.env.{stamp}.bak"
    shutil.copy2(LEGACY_ENV, backup)
    backup.chmod(0o600)
    LEGACY_ENV.unlink()
    print(
        "Migrated common.env to owner configuration files. Original backup: "
        f"{backup.relative_to(ROOT)}"
    )
    return migrated


def main():
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "init":
        initialize()
        return 0
    if len(sys.argv) > 1 and sys.argv[1] == "show":
        values = load_values(process_env=False)
        for key in sorted(values):
            print(f"{key}=<set>")
        return 0
    print("Usage: opendock-settings.py init|show")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
