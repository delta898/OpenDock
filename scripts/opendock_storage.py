#!/usr/bin/env python3
"""Resolve and validate service-declared host storage mounts."""

import os
from pathlib import Path


def resolve_mount_source(service, mount, values):
    """Return a normalized host path for one declared Compose storage mount."""
    key = mount["setting_key"]
    value = values.get(key, "").strip()
    if not value:
        field = next(item for item in service.setup_fields if item["name"] == key)
        value = field["default"]
    if "~" in value:
        raise ValueError(
            f"{key} must use an absolute path (for example /mnt/media), not '~'."
        )

    path = Path(value)
    if path.is_absolute():
        if ".." in path.parts:
            raise ValueError(f"{key} cannot contain '..' path components.")
        return path
    if ".." in path.parts:
        raise ValueError(
            f"{key} must be an absolute path or stay inside services/{service.name}/."
        )
    return service.directory / path


def symlink_component(path):
    """Return the first symlink in an absolute path, if any."""
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        if current.is_symlink():
            return current
    return None


def validate_mounts(service, values):
    """Return actionable configuration issues for the service's storage mounts."""
    issues = []
    for mount in service.storage_mounts:
        key = mount["setting_key"]
        try:
            path = resolve_mount_source(service, mount, values)
        except (KeyError, ValueError) as error:
            issues.append(str(error))
            continue
        linked = symlink_component(path)
        if linked:
            issues.append(f"{key} points through a symlink: {linked}")
            continue
        if not path.exists():
            field = next(item for item in service.setup_fields if item["name"] == key)
            configured = values.get(key, "").strip()
            if configured and configured != field["default"]:
                issues.append(
                    f"{key} directory does not exist: {path}. Create the configured directory first."
                )
                continue
            # OpenDock creates a missing checkout-local default during launch/up.
            continue
        if not path.is_dir():
            issues.append(f"{key} is not a directory: {path}")
            continue
        resolved = path.resolve()
        if path.is_mount():
            issues.append(
                f"{key} points at a filesystem root: {path}. Choose a dedicated directory inside it."
            )
            continue
        home = Path.home().resolve()
        if resolved == Path(resolved.anchor) or resolved == home or home.is_relative_to(resolved):
            issues.append(f"{key} is too broad to use as a service data directory: {path}")
            continue
        try:
            relative = resolved.relative_to(service.directory.resolve())
        except ValueError:
            relative = None
        if relative is not None:
            declared_paths = service.removal.get("data_paths", ())
            if not any(
                relative == Path(item) or Path(item) in relative.parents
                for item in declared_paths
            ):
                issues.append(
                    f"{key} is inside the checkout but outside declared removal.data_paths: {path}"
                )
                continue
        access = mount["access"]
        mode = os.R_OK | os.X_OK
        if access == "read-write":
            mode |= os.W_OK
        if not os.access(path, mode):
            issues.append(f"{key} directory is not accessible for {access} use: {path}")
    return issues


def prepare_default_mounts(service, values):
    """Create missing checkout-local defaults, never user-selected host paths."""
    created = []
    for mount in service.storage_mounts:
        key = mount["setting_key"]
        field = next(item for item in service.setup_fields if item["name"] == key)
        default = field["default"]
        configured = values.get(key, "").strip()
        if configured and configured != default:
            continue
        path = resolve_mount_source(service, mount, values)
        linked = symlink_component(path)
        if linked:
            raise ValueError(f"Refusing to prepare storage path through a symlink: {linked}")
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            created.append(path)
    return created


def external_paths_for_removal(service, values):
    """Return mount paths outside the service checkout that complete removal owns."""
    results = []
    service_root = service.directory.resolve()
    for mount in service.storage_mounts:
        path = resolve_mount_source(service, mount, values)
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(service_root)
        except ValueError:
            relative = None
        if relative is not None:
            declared_paths = service.removal.get("data_paths", ())
            if not any(
                relative == Path(item) or Path(item) in relative.parents
                for item in declared_paths
            ):
                raise ValueError(
                    f"{mount['setting_key']} is inside the checkout but outside "
                    f"declared removal.data_paths: {path}"
                )
            continue
        if not path.exists() and not path.is_symlink():
            results.append({"mount": mount, "path": path, "exists": False})
            continue
        linked = symlink_component(path)
        if linked:
            raise ValueError(f"Refusing to remove storage path through a symlink: {linked}")
        if not path.is_dir():
            raise ValueError(f"Configured storage path is not a directory: {path}")
        if path.is_mount():
            raise ValueError(
                f"Refusing to remove mounted filesystem root {path}; configure a directory inside it."
            )
        home = Path.home().resolve()
        if resolved == Path(resolved.anchor) or home == resolved or home.is_relative_to(resolved):
            raise ValueError(f"Refusing to remove a filesystem root or home directory: {path}")
        results.append({"mount": mount, "path": path, "exists": True})
    return results
