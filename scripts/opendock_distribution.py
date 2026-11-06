"""Static catalog client and verified service package installer."""

from __future__ import annotations

import hashlib
import datetime
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile


class DistributionError(ValueError):
    """Invalid catalog, unavailable artifact, or unsafe package."""


MAX_CATALOG_BYTES = 4 * 1024 * 1024
MAX_PACKAGE_BYTES = 128 * 1024 * 1024
MAX_EXPANDED_BYTES = 512 * 1024 * 1024
ID_RE = re.compile(r"[a-z][a-z0-9-]*\Z")
VERSION_RE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?\Z")


def catalog_url(environment: str) -> str:
    if environment not in {"dev", "prod"}:
        raise DistributionError("Catalog environment must be dev or prod.")
    from opendock_settings import load_values

    key = f"OPENDOCK_{environment.upper()}_CATALOG_BASE_URL"
    base = load_values().get(key, "").strip()
    if not base:
        raise DistributionError(
            f"No {environment} catalog URL is configured. Set {key} "
            "in config/core.env to the public R2 URL."
        )
    parsed = urllib.parse.urlsplit(base)
    if parsed.scheme != "https" or not parsed.netloc or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise DistributionError(f"{key} must be an HTTPS origin without a path, query, or fragment.")
    return base.rstrip("/") + "/catalog/v1/index.json"


def cache_path(environment: str) -> Path:
    root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return root / "opendock" / environment / "catalog-v1.json"


def validate_catalog(raw: bytes) -> dict:
    if len(raw) > MAX_CATALOG_BYTES:
        raise DistributionError("Catalog exceeds the 4 MiB size limit.")
    try:
        catalog = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DistributionError(f"Catalog is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(catalog, dict) or catalog.get("catalog_schema_version") != 1:
        raise DistributionError("Unsupported catalog schema; expected version 1.")
    services = catalog.get("services")
    if not isinstance(services, list):
        raise DistributionError("Catalog must contain a services array.")
    seen = set()
    for service in services:
        if not isinstance(service, dict):
            raise DistributionError("Catalog contains an invalid service entry.")
        sid = service.get("service_id")
        if not isinstance(sid, str) or not ID_RE.fullmatch(sid) or sid in seen:
            raise DistributionError(f"Invalid or duplicate service ID: {sid!r}.")
        seen.add(sid)
        if not isinstance(service.get("display_name"), str):
            raise DistributionError(f"Catalog service {sid!r} has no display_name.")
        releases = service.get("releases")
        if not isinstance(releases, list):
            raise DistributionError(f"Catalog service {sid!r} has invalid releases.")
        versions = set()
        for release in releases:
            if not isinstance(release, dict):
                raise DistributionError(f"Catalog service {sid!r} has an invalid release.")
            version, artifact, digest = (release.get(k) for k in ("version", "artifact", "sha256"))
            key = PurePosixPath(artifact) if isinstance(artifact, str) else None
            if (not isinstance(version, str) or not VERSION_RE.fullmatch(version) or version in versions
                    or key is None or key.is_absolute() or ".." in key.parts
                    or key.parts[:1] != ("packages",) or key.parts[1:2] != (sid,)
                    or not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest)):
                raise DistributionError(f"Catalog service {sid!r} has invalid release metadata.")
            if type(release.get("size_bytes")) is not int or not 1 <= release["size_bytes"] <= MAX_PACKAGE_BYTES:
                raise DistributionError(f"Catalog service {sid!r} has invalid package size.")
            versions.add(version)
    return catalog


def fetch_catalog(environment: str, *, force: bool = True) -> tuple[dict, Path]:
    destination = cache_path(environment)
    if not force and destination.is_file():
        return validate_catalog(destination.read_bytes()), destination
    url = catalog_url(environment)
    request = urllib.request.Request(url, headers={"User-Agent": "OpenDock/1 catalog-client"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read(MAX_CATALOG_BYTES + 1)
    except (OSError, urllib.error.URLError) as exc:
        raise DistributionError(f"Could not fetch {environment} catalog: {exc}") from exc
    catalog = validate_catalog(raw)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(".tmp")
    temp.write_bytes(raw)
    os.replace(temp, destination)
    return catalog, destination


def load_cached(environment: str) -> dict:
    path = cache_path(environment)
    if not path.is_file():
        return fetch_catalog(environment)[0]
    return validate_catalog(path.read_bytes())


def _safe_extract(archive: zipfile.ZipFile, destination: Path) -> None:
    seen = set()
    expanded = 0
    for member in archive.infolist():
        name = member.filename
        path = PurePosixPath(name)
        mode = member.external_attr >> 16
        if (not name or path.is_absolute() or ".." in path.parts or "\\" in name
                or name in seen or mode & 0o170000 == 0o120000):
            raise DistributionError(f"Package contains an unsafe ZIP entry: {name!r}.")
        seen.add(name)
        expanded += member.file_size
        if expanded > MAX_EXPANDED_BYTES:
            raise DistributionError("Package exceeds the 512 MiB expanded size limit.")
        target = destination.joinpath(*path.parts)
        if member.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member) as source, target.open("xb") as output:
            shutil.copyfileobj(source, output)


def install(environment: str, service_id: str, catalog: dict, root: Path) -> Path:
    if not ID_RE.fullmatch(service_id):
        raise DistributionError("Invalid service ID.")
    item = next((s for s in catalog["services"] if s["service_id"] == service_id), None)
    if item is None:
        raise DistributionError(f"Service {service_id!r} is not in the catalog.")
    candidates = [r for r in item["releases"] if "-" not in r["version"]]
    if not candidates:
        raise DistributionError(f"Service {service_id!r} has no stable release.")
    release = max(candidates, key=lambda r: tuple(map(int, r["version"].split("."))))
    base = catalog_url(environment).rsplit("/catalog/v1/index.json", 1)[0]
    url = base + "/" + urllib.parse.quote(release["artifact"], safe="/")
    request = urllib.request.Request(url, headers={"User-Agent": "OpenDock/1 package-installer"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = response.read(MAX_PACKAGE_BYTES + 1)
    except (OSError, urllib.error.URLError) as exc:
        raise DistributionError(f"Could not download {service_id} package: {exc}") from exc
    if len(payload) != release["size_bytes"] or len(payload) > MAX_PACKAGE_BYTES:
        raise DistributionError("Downloaded package size does not match the catalog.")
    if hashlib.sha256(payload).hexdigest() != release["sha256"]:
        raise DistributionError("Package SHA-256 does not match the catalog.")

    target_parent = root / "services" / "extensions" / service_id / "releases"
    target = target_parent / release["version"]
    if target.exists():
        raise DistributionError(f"{service_id} {release['version']} is already installed.")
    target_parent.mkdir(parents=True, exist_ok=True)
    staging_parent = target_parent.parent / ".staging"
    staging_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="package-", dir=staging_parent) as temporary:
        stage = Path(temporary) / "release"
        stage.mkdir()
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                _safe_extract(archive, stage)
        except (zipfile.BadZipFile, OSError) as exc:
            raise DistributionError(f"Package ZIP is invalid: {exc}") from exc
        descriptor = stage / "opendock.toml"
        compose = stage / "compose.yml"
        if not descriptor.is_file() or not compose.is_file():
            raise DistributionError("Package must contain opendock.toml and compose.yml at its root.")
        try:
            import tomllib
            metadata = tomllib.loads(descriptor.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise DistributionError(f"Package descriptor is invalid: {exc}") from exc
        if metadata.get("service_id") != service_id:
            raise DistributionError("Package descriptor service_id does not match catalog.")
        if metadata.get("version") != release["version"]:
            raise DistributionError("Package descriptor version does not match catalog.")
        os.replace(stage, target)
    registry = root / "services" / "extensions" / "installed.toml"
    entries = []
    if registry.exists():
        import tomllib
        try:
            entries = tomllib.loads(registry.read_text()).get("extensions", [])
        except (OSError, ValueError) as exc:
            raise DistributionError(f"Installed package registry is invalid: {exc}") from exc
    if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
        raise DistributionError("Installed package registry has invalid entries.")
    entries = [entry for entry in entries if entry.get("service_id") != service_id]
    entries.append({
        "service_id": service_id,
        "version": release["version"],
        "release_path": f"services/extensions/{service_id}/releases/{release['version']}",
        "sha256": release["sha256"],
        "installed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    })
    registry.parent.mkdir(parents=True, exist_ok=True)
    body = ["schema_version = 1", ""]
    for entry in sorted(entries, key=lambda value: value["service_id"]):
        body.extend(("[[extensions]]",))
        for key in ("service_id", "version", "release_path", "sha256", "installed_at"):
            body.append(f"{key} = {json.dumps(entry[key])}")
        body.append("")
    temp_registry = registry.with_suffix(".toml.tmp")
    temp_registry.write_text("\n".join(body), encoding="utf-8")
    try:
        os.replace(temp_registry, registry)
    except OSError:
        shutil.rmtree(target, ignore_errors=True)
        temp_registry.unlink(missing_ok=True)
        raise
    return target
