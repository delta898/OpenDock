"""Resolve the active checkout root consistently across CLI helper processes."""

import os
from pathlib import Path


def resolve_root(source_file: str | Path) -> Path:
    """Use an explicit checkout root when set, otherwise locate the code checkout."""
    override = os.environ.get("OPENDOCK_ROOT", "").strip()
    if override:
        root = Path(override).expanduser().resolve()
        if not (root / "opendock").is_file() or not (root / "scripts").is_dir():
            raise RuntimeError(f"OPENDOCK_ROOT is not an OpenDock checkout: {root}")
        return root
    source = Path(source_file).resolve()
    return source.parent if source.name == "opendock" else source.parents[1]


def local_test_enabled() -> bool:
    return os.environ.get("OPENDOCK_LOCAL_TEST") == "1"


def compose_project(target: str) -> str:
    """Return a checkout-scoped Compose project name."""
    base = target.lower().replace("_", "-")
    suffix = os.environ.get("OPENDOCK_COMPOSE_SUFFIX", "").strip().lower()
    if not suffix:
        return base
    if not suffix.replace("-", "").isalnum():
        raise RuntimeError("OPENDOCK_COMPOSE_SUFFIX must contain only letters, digits, and hyphens.")
    return f"od-{suffix[:20]}-{base}"[:63].rstrip("-")


def local_test_mount(path: str | Path, root: str | Path) -> Path:
    """Resolve a mount and refuse any host path outside the disposable checkout."""
    resolved_root = Path(root).resolve()
    resolved_path = Path(path).resolve()
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise RuntimeError(
            f"Local test mode refuses host mount outside its checkout: {resolved_path}"
        ) from exc
    return resolved_path
