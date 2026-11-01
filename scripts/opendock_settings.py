#!/usr/bin/env python3
"""Load, migrate, and update OpenDock's layered environment configuration."""

import json
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
SERVICE_DEFAULT_MIGRATION_MARKER = CONFIG / ".service-default-migration-v1"

SERVICE_NAMES = (
    "wordpress", "nextcloud", "immich", "jellyfin", "mastodon",
    "mattermost", "n8n", "uptime-kuma", "homepage", "supabase", "hermes",
)
SERVICE_PREFIXES = {
    service: service.replace("-", "_").upper() + "_"
    for service in SERVICE_NAMES
}
INFRA_KEYS = {
    "MARIADB_ROOT_PASSWORD", "POSTGRES_ADMIN_USER", "POSTGRES_ADMIN_PASSWORD",
    "MARIADB_VERSION", "POSTGRES_VERSION", "REDIS_VERSION",
}
GATEWAY_KEYS = {"CADDY_VERSION", "HTTP_PORT", "HTTPS_PORT"}
MAIL_PREFIX = "SMTP_"
DATABASE_SHARED_KEYS = {"MARIADB_CLIENT_VERSION"}


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
    if key in GATEWAY_KEYS:
        return Path("config") / "gateway.env"
    if key.startswith(MAIL_PREFIX):
        return Path("config") / "shared" / "mail.env"
    if key in DATABASE_SHARED_KEYS:
        return Path("config") / "shared" / "database.env"
    for service, prefix in SERVICE_PREFIXES.items():
        if key.startswith(prefix):
            return Path("services") / service / ".env"
    raise ValueError(f"No configuration owner is registered for key: {key}")


def config_paths(service=None, examples=False):
    if examples:
        relative = [
            Path("core.env.default"), Path("infra.env.default"),
            Path("shared") / "mail.env.default",
            Path("shared") / "database.env.default",
        ]
        if service in (None, "gateway"):
            relative.insert(2, Path("gateway.env.default"))
    else:
        relative = [
            Path("core.env"), Path("infra.env"),
            Path("shared") / "mail.env",
            Path("shared") / "database.env",
        ]
        if service in (None, "gateway"):
            relative.insert(2, Path("gateway.env"))
    selected = SERVICE_NAMES if service is None else (service,)
    paths = [CONFIG / path for path in relative]
    for name in selected:
        if name not in SERVICE_PREFIXES or not examples:
            continue
        paths.append(ROOT / "services" / name / ".env.default")
    return paths


def load_values(service=None, *, examples=False, process_env=False, legacy=True):
    values = {}
    # Tracked defaults provide the baseline; local values override them.
    for path in config_paths(service, examples=True):
        values.update(parse_env(path))
    if examples:
        return values
    if legacy and LEGACY_ENV.is_file():
        values.update(parse_env(LEGACY_ENV))
    if legacy and service in (None, "infra"):
        values.update(parse_env(ROOT / "infra" / ".env"))
    if legacy and service in (None, "gateway"):
        values.update(parse_env(ROOT / "gateway" / ".env"))
    if service in SERVICE_PREFIXES:
        values.update(parse_env(CONFIG / "services" / f"{service}.env"))
    elif service is None:
        for name in SERVICE_NAMES:
            values.update(parse_env(CONFIG / "services" / f"{name}.env"))
    for path in config_paths(service):
        values.update(parse_env(path))
    if service in SERVICE_PREFIXES:
        values.update(parse_env(ROOT / "services" / service / ".env"))
    elif service is None:
        # Current service-local overrides have the highest file precedence.
        for name in SERVICE_NAMES:
            values.update(parse_env(ROOT / "services" / name / ".env"))
    if process_env:
        values.update(os.environ)
    return values


def compose_env_files(service=None):
    defaults = [
        CONFIG / "core.env.default", CONFIG / "infra.env.default",
        CONFIG / "shared" / "mail.env.default",
        CONFIG / "shared" / "database.env.default",
    ]
    if service == "gateway":
        defaults.insert(2, CONFIG / "gateway.env.default")
    if service in SERVICE_PREFIXES:
        defaults.append(ROOT / "services" / service / ".env.default")
    local_config = [
        CONFIG / "core.env", CONFIG / "infra.env",
        CONFIG / "shared" / "mail.env", CONFIG / "shared" / "database.env",
    ]
    if service == "gateway":
        local_config.insert(2, CONFIG / "gateway.env")
    files = [path for path in defaults + local_config if path.is_file()]
    # Read-only compatibility for commands run before first setup/migration.
    if LEGACY_ENV.is_file():
        files.append(LEGACY_ENV)
    if service:
        # A leftover private config from the old location must override common.env.
        legacy_service = CONFIG / "services" / f"{service}.env"
        if legacy_service.is_file():
            files.append(legacy_service)
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
    """Prepare config directories and migrate legacy service and common env files."""
    if CONFIG.is_symlink():
        raise ValueError(f"Refusing to initialize config through a symlink: {CONFIG}")
    CONFIG.mkdir(parents=True, exist_ok=True)
    for directory in (CONFIG / "shared", CONFIG / "services"):
        if directory.is_symlink():
            raise ValueError(f"Refusing to initialize config through a symlink: {directory}")
    for path in config_paths(examples=False):
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_symlink():
            raise ValueError(f"Refusing to initialize config through a symlink: {path}")
    for name in SERVICE_NAMES:
        local = ROOT / "services" / name / ".env"
        if local.is_symlink():
            raise ValueError(f"Refusing to initialize config through a symlink: {local}")

    if LEGACY_ENV.is_symlink():
        raise ValueError(f"Refusing to migrate legacy config through a symlink: {LEGACY_ENV}")

    legacy = parse_env(LEGACY_ENV) if LEGACY_ENV.is_file() else None
    # Validate the complete legacy root file before changing any old service
    # files, so an unknown key remains a fail-safe stop with no migration side effects.
    if legacy is not None:
        for key in legacy:
            owner_path(key)

    migrated = migrate_legacy_service_configs()
    migrate_legacy_service_defaults()
    migrate_legacy_infra_defaults()
    migrate_legacy_gateway_defaults()
    migrate_legacy_gateway_defaults()
    if legacy is None:
        return migrated

    grouped = {}
    for key, value in legacy.items():
        grouped.setdefault(owner_path(key), {})[key] = value

    # Legacy values win over example placeholders but never overwrite an
    # already-created split setting. This makes a partially migrated install safe.
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


def migrate_legacy_service_configs():
    """Move old config/services/*.env overrides into each service's private .env."""
    legacy_dir = CONFIG / "services"
    if legacy_dir.is_symlink():
        raise ValueError(f"Refusing to migrate service config through a symlink: {legacy_dir}")

    sources = []
    incoming = {}
    origin = {}
    for service in SERVICE_NAMES:
        source = legacy_dir / f"{service}.env"
        if not source.is_file():
            continue
        if source.is_symlink():
            raise ValueError(f"Refusing to migrate service config through a symlink: {source}")
        sources.append(source)
        for key, value in parse_env(source).items():
            relative = owner_path(key)
            if relative.parts[:2] == ("services", service):
                pass
            elif key in DATABASE_SHARED_KEYS and service in {"wordpress", "nextcloud"}:
                pass
            else:
                raise ValueError(
                    f"Unexpected key {key} in legacy service config {source.relative_to(ROOT)}"
                )
            existing_source = origin.get((relative, key))
            if existing_source and incoming[(relative, key)] != value:
                raise ValueError(
                    f"Conflicting legacy values for {key} in "
                    f"{existing_source.relative_to(ROOT)} and {source.relative_to(ROOT)}"
                )
            incoming[(relative, key)] = value
            origin[(relative, key)] = source

    if not sources:
        return []

    by_destination = {}
    for (relative, key), value in incoming.items():
        by_destination.setdefault(ROOT / relative, {})[key] = value

    migrated = []
    for destination, values in by_destination.items():
        current = parse_env(destination)
        pending = {key: value for key, value in values.items() if key not in current}
        migrated.extend(_write_values(destination, pending))

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup_root = BACKUPS / "legacy-services"
    for source in sources:
        backup = backup_root / f"{source.stem}.{stamp}.bak"
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, backup)
        backup.chmod(0o600)
        source.unlink()
    print(
        f"Migrated {len(sources)} legacy service config file(s) to service-owned files. "
        f"Restricted backups: {backup_root.relative_to(ROOT)}"
    )
    return migrated


def migrate_legacy_service_defaults():
    """Drop old tracked defaults accidentally carried as private overrides once."""
    marker = CONFIG / SERVICE_DEFAULT_MIGRATION_MARKER.name
    if marker.is_symlink():
        raise ValueError(f"Refusing to migrate through a symlink: {marker}")
    if marker.is_file():
        return

    backup_root = BACKUPS / "legacy-service-defaults"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    migration_file = CONFIG / "migrations" / "service-env-v1.json"
    legacy_defaults = json.loads(migration_file.read_text()) if migration_file.is_file() else {}
    cleaned = []
    for service in SERVICE_NAMES:
        local = ROOT / "services" / service / ".env"
        defaults = ROOT / "services" / service / ".env.default"
        if local.is_symlink():
            raise ValueError(f"Refusing to migrate service config through a symlink: {local}")
        if not local.is_file() or not defaults.is_file():
            continue

        default_values = parse_env(defaults)
        previous_values = legacy_defaults.get(service, {})
        kept_lines = []
        removed_keys = []
        for raw in local.read_text().splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                normalized = value.strip().strip("\"'")
                normalized_key = key.strip()
                if (
                    default_values.get(normalized_key) == normalized
                    or previous_values.get(normalized_key) == normalized
                ):
                    removed_keys.append(normalized_key)
                    continue
            kept_lines.append(raw)
        if not removed_keys:
            continue

        backup = backup_root / f"{service}.env.{stamp}.bak"
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local, backup)
        backup.chmod(0o600)
        content = "\n".join(kept_lines).rstrip()
        if content:
            local.write_text(content + "\n")
            local.chmod(0o600)
        else:
            local.unlink()
        cleaned.append((service, len(removed_keys)))

    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("Service defaults migration completed.\n")
    marker.chmod(0o600)
    for service, count in cleaned:
        print(
            f"Moved {count} unchanged default value(s) from services/{service}/.env "
            f"back to its tracked .env.default."
        )
    if cleaned:
        print(f"Restricted backups: {backup_root.relative_to(ROOT)}")


def migrate_legacy_infra_defaults():
    """Move the former tracked infra/.env into shared infra config once."""
    marker = CONFIG / ".infra-default-migration-v1"
    if marker.is_symlink():
        raise ValueError(f"Refusing to migrate through a symlink: {marker}")
    if marker.is_file():
        return

    old_file = ROOT / "infra" / ".env"
    if old_file.is_symlink():
        raise ValueError(f"Refusing to migrate legacy infra config through a symlink: {old_file}")
    if old_file.is_file():
        legacy_file = CONFIG / "migrations" / "infra-env-v1.json"
        previous_values = json.loads(legacy_file.read_text()) if legacy_file.is_file() else {}
        current_defaults = parse_env(CONFIG / "infra.env.default")
        custom_values = {}
        for key, value in parse_env(old_file).items():
            if owner_path(key) != Path("config/infra.env"):
                raise ValueError(f"Unexpected key {key} in legacy infra/.env")
            if value not in (current_defaults.get(key), previous_values.get(key)):
                custom_values[key] = value

        destination = CONFIG / "infra.env"
        current = parse_env(destination)
        pending = {key: value for key, value in custom_values.items() if key not in current}
        _write_values(destination, pending)

        backup = BACKUPS / "legacy-infra" / f"infra.env.{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.bak"
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old_file, backup)
        backup.chmod(0o600)
        old_file.unlink()
        print(
            "Migrated legacy infra/.env to config/infra.env. "
            f"Restricted backup: {backup.relative_to(ROOT)}"
        )

    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("Infra defaults migration completed.\n")
    marker.chmod(0o600)


def migrate_legacy_gateway_defaults():
    """Move the former tracked gateway/.env into shared gateway config once."""
    marker = CONFIG / ".gateway-default-migration-v1"
    if marker.is_symlink():
        raise ValueError(f"Refusing to migrate through a symlink: {marker}")
    if marker.is_file():
        return

    old_file = ROOT / "gateway" / ".env"
    if old_file.is_symlink():
        raise ValueError(f"Refusing to migrate legacy gateway config through a symlink: {old_file}")
    if old_file.is_file():
        legacy_file = CONFIG / "migrations" / "gateway-env-v1.json"
        previous_values = json.loads(legacy_file.read_text()) if legacy_file.is_file() else {}
        current_defaults = parse_env(CONFIG / "gateway.env.default")
        custom_values = {}
        for key, value in parse_env(old_file).items():
            if owner_path(key) != Path("config/gateway.env"):
                raise ValueError(f"Unexpected key {key} in legacy gateway/.env")
            if value not in (current_defaults.get(key), previous_values.get(key)):
                custom_values[key] = value

        destination = CONFIG / "gateway.env"
        current = parse_env(destination)
        pending = {key: value for key, value in custom_values.items() if key not in current}
        _write_values(destination, pending)

        backup = BACKUPS / "legacy-gateway" / f"gateway.env.{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.bak"
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old_file, backup)
        backup.chmod(0o600)
        old_file.unlink()
        print(
            "Migrated legacy gateway/.env to config/gateway.env. "
            f"Restricted backup: {backup.relative_to(ROOT)}"
        )

    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("Gateway defaults migration completed.\n")
    marker.chmod(0o600)


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
