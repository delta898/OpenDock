#!/usr/bin/env python3
"""Discover Compose-backed services without maintaining a central name list."""

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - OpenDock requires Python 3.11+
    tomllib = None


class CatalogError(ValueError):
    """Raised when a service descriptor is malformed or unsupported."""


@dataclass(frozen=True)
class ServiceDefinition:
    """Filesystem identity and optional descriptor for one service."""

    name: str
    directory: Path
    compose_file: Path
    descriptor_file: Path
    descriptor: Mapping[str, object]

    @property
    def capabilities(self) -> tuple[str, ...]:
        return tuple(self.descriptor.get("capabilities", ()))

    @property
    def dependencies(self) -> tuple[str, ...]:
        return tuple(self.descriptor.get("dependencies", ()))

    @property
    def display_name(self) -> str:
        return str(self.descriptor.get("display_name", self.name))

    @property
    def setup_fields(self) -> tuple[Mapping[str, object], ...]:
        setup = self.descriptor.get("setup", {})
        return tuple(setup.get("fields", ()))

    @property
    def setup_dependencies(self) -> tuple[str, ...]:
        setup = self.descriptor.get("setup", {})
        return tuple(setup.get("dependencies", ()))


class ServiceCatalog:
    """Read-only catalog derived from services/<name>/compose.yml."""

    DESCRIPTOR_NAME = "opendock.toml"
    DESCRIPTOR_VERSION = 1
    CAPABILITY_API_VERSION = 1
    SETUP_FIELD_KINDS = frozenset({
        "required-user", "defaulted-choice", "initial-credential",
        "secret-user", "generated-secret",
    })
    SETUP_DEPENDENCIES = frozenset({"mariadb", "postgres"})
    # Add a capability here only when its handler contract and common dispatcher
    # are implemented. Unknown declarations must fail instead of being ignored.
    CAPABILITIES = frozenset({"runtime_environment", "prepare"})

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.services_dir = self.root / "services"
        self._services = self._discover()
        self._by_name = {service.name: service for service in self._services}
        self._validate_dependencies()

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._by_name)

    @property
    def services(self) -> tuple[ServiceDefinition, ...]:
        return self._services

    def get(self, name: str) -> ServiceDefinition:
        try:
            return self._by_name[name]
        except KeyError as exc:
            raise CatalogError(f"Unknown service: {name}") from exc

    def _validate_dependencies(self) -> None:
        known = set(self._by_name) | {"infra", "gateway"}
        for service in self._services:
            unknown = sorted(set(service.dependencies) - known)
            if unknown:
                raise CatalogError(
                    f"Service {service.name!r} declares unknown dependencies: {', '.join(unknown)}"
                )

    def _discover(self) -> tuple[ServiceDefinition, ...]:
        if not self.services_dir.is_dir():
            return ()

        found = []
        for compose_file in sorted(self.services_dir.glob("*/compose.yml")):
            directory = compose_file.parent
            descriptor_file = directory / self.DESCRIPTOR_NAME
            if not descriptor_file.is_file():
                raise CatalogError(
                    f"Service {directory.name!r} is missing its descriptor: "
                    f"{descriptor_file.relative_to(self.root)}."
                )
            descriptor = self._load_descriptor(descriptor_file, directory.name)
            found.append(ServiceDefinition(
                name=directory.name,
                directory=directory,
                compose_file=compose_file,
                descriptor_file=descriptor_file,
                descriptor=MappingProxyType(descriptor),
            ))
        return tuple(found)

    def _load_descriptor(self, path: Path, service_id: str) -> dict[str, object]:
        if not path.is_file():
            return {}
        if tomllib is None:
            raise CatalogError(
                f"Reading {path.relative_to(self.root)} requires Python 3.11 or newer."
            )
        try:
            with path.open("rb") as stream:
                descriptor = tomllib.load(stream)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise CatalogError(f"Invalid service descriptor {path}: {exc}") from exc

        version = descriptor.get("schema_version")
        if type(version) is not int or version != self.DESCRIPTOR_VERSION:
            raise CatalogError(
                f"Unsupported schema_version {version!r} in {path}; "
                f"this OpenDock supports version {self.DESCRIPTOR_VERSION}."
            )

        declared_id = descriptor.get("service_id")
        if declared_id != service_id:
            raise CatalogError(
                f"Service descriptor {path} must declare service_id = {service_id!r}."
            )

        capabilities = descriptor.get("capabilities", [])
        if (not isinstance(capabilities, list)
                or any(not isinstance(item, str) for item in capabilities)):
            raise CatalogError(f"Service descriptor {path} must declare capabilities as a string list.")
        if len(capabilities) != len(set(capabilities)):
            raise CatalogError(f"Service descriptor {path} contains duplicate capabilities.")
        unknown = sorted(set(capabilities) - self.CAPABILITIES)
        if unknown:
            raise CatalogError(
                f"Service descriptor {path} declares unsupported capabilities: {', '.join(unknown)}"
            )

        api_version = descriptor.get("capability_api_version")
        if capabilities:
            if type(api_version) is not int or api_version != self.CAPABILITY_API_VERSION:
                raise CatalogError(
                    f"Service descriptor {path} requires capability API {api_version!r}; "
                    f"this OpenDock supports API {self.CAPABILITY_API_VERSION}."
                )

        dependencies = descriptor.get("dependencies", [])
        if (not isinstance(dependencies, list)
                or any(not isinstance(item, str) or not item for item in dependencies)):
            raise CatalogError(f"Service descriptor {path} must declare dependencies as a string list.")
        if len(dependencies) != len(set(dependencies)):
            raise CatalogError(f"Service descriptor {path} contains duplicate dependencies.")
        unsupported_dependencies = sorted(set(dependencies) - {"infra", "gateway"})
        if unsupported_dependencies:
            raise CatalogError(
                f"Service descriptor {path} declares unsupported platform dependencies: "
                f"{', '.join(unsupported_dependencies)}"
            )

        display_name = descriptor.get("display_name", service_id)
        if not isinstance(display_name, str) or not display_name.strip():
            raise CatalogError(f"Service descriptor {path} has an invalid display_name.")

        setup = descriptor.get("setup", {})
        if not isinstance(setup, dict):
            raise CatalogError(f"Service descriptor {path} has an invalid [setup] section.")
        setup_fields = setup.get("fields", [])
        if not isinstance(setup_fields, list):
            raise CatalogError(f"Service descriptor {path} setup.fields must be an array of tables.")
        setup_dependencies = setup.get("dependencies", [])
        if (not isinstance(setup_dependencies, list)
                or any(not isinstance(item, str) for item in setup_dependencies)):
            raise CatalogError(
                f"Service descriptor {path} setup.dependencies must be a string list."
            )
        unknown_setup_dependencies = sorted(
            set(setup_dependencies) - self.SETUP_DEPENDENCIES
        )
        if unknown_setup_dependencies:
            raise CatalogError(
                f"Service descriptor {path} declares unsupported setup dependencies: "
                f"{', '.join(unknown_setup_dependencies)}"
            )
        if len(setup_dependencies) != len(set(setup_dependencies)):
            raise CatalogError(f"Service descriptor {path} contains duplicate setup dependencies.")
        prefix = service_id.replace("-", "_").upper() + "_"
        seen_fields = set()
        for field in setup_fields:
            if not isinstance(field, dict):
                raise CatalogError(f"Service descriptor {path} contains an invalid setup field.")
            name = field.get("name")
            kind = field.get("kind")
            if not isinstance(name, str) or not name.startswith(prefix):
                raise CatalogError(
                    f"Setup fields in {path} must use the {prefix} key prefix."
                )
            if name in seen_fields:
                raise CatalogError(f"Service descriptor {path} repeats setup field {name!r}.")
            seen_fields.add(name)
            if not isinstance(kind, str) or kind not in self.SETUP_FIELD_KINDS:
                raise CatalogError(
                    f"Setup field {name!r} in {path} has unsupported kind {kind!r}."
                )
            for attribute in ("default", "note", "change_notice"):
                value = field.get(attribute)
                if value is not None and not isinstance(value, str):
                    raise CatalogError(
                        f"Setup field {name!r} in {path} has a non-string {attribute}."
                    )
            if kind == "defaulted-choice" and not isinstance(field.get("default"), str):
                raise CatalogError(
                    f"Setup field {name!r} in {path} needs a string default."
                )
        return descriptor


def service_names(root: Path) -> tuple[str, ...]:
    """Return discovered service names in stable sorted order."""
    return ServiceCatalog(root).names
