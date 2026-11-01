#!/usr/bin/env python3
"""Discover Compose-backed services without maintaining a central name list."""

from dataclasses import dataclass
import os
from pathlib import Path
from pathlib import PurePosixPath
import re
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

    @property
    def removal(self) -> Mapping[str, object]:
        return self.descriptor.get("removal", {})

    @property
    def commands(self) -> tuple[Mapping[str, object], ...]:
        return tuple(self.descriptor.get("commands", ()))


@dataclass(frozen=True)
class PlatformComponentDefinition:
    """Declarative configuration owned by a root-level platform component."""

    name: str
    directory: Path
    descriptor_file: Path
    descriptor: Mapping[str, object]

    @property
    def setting_keys(self) -> tuple[str, ...]:
        return tuple(self.descriptor.get("setting_keys", ()))

    @property
    def config_file(self) -> str:
        return str(self.descriptor["config_file"])

    @property
    def shared_groups(self) -> tuple[str, ...]:
        return tuple(self.descriptor.get("shared_groups", ()))

    @property
    def setup_fields(self) -> tuple[Mapping[str, object], ...]:
        setup = self.descriptor.get("setup", {})
        return tuple(setup.get("fields", ()))

    @property
    def shared_settings(self) -> tuple[Mapping[str, object], ...]:
        return tuple(self.descriptor.get("shared_settings", ()))


class PlatformCatalog:
    """Discover root-level platform descriptors independently of app services."""

    DESCRIPTOR_VERSION = 1

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self._components = {}
        for path in sorted(self.root.glob("*/opendock.toml")):
            if not (path.parent / "compose.yml").is_file():
                continue
            component = self._load(path, path.parent.name)
            self._components[component.name] = component
        groups = [
            group for component in self.components for group in component.shared_groups
        ]
        if len(groups) != len(set(groups)):
            raise CatalogError("Platform descriptors declare duplicate shared groups.")
        keys = [
            key
            for component in self.components
            for key in (
                *component.setting_keys,
                *(item["name"] for item in component.shared_settings),
            )
        ]
        if len(keys) != len(set(keys)):
            raise CatalogError("Platform descriptors declare duplicate setting ownership.")

    @property
    def components(self) -> tuple[PlatformComponentDefinition, ...]:
        return tuple(self._components.values())

    def get(self, name: str) -> PlatformComponentDefinition:
        try:
            return self._components[name]
        except KeyError as exc:
            raise CatalogError(f"Unknown platform component: {name}") from exc

    def _load(self, path: Path, name: str) -> PlatformComponentDefinition:
        if tomllib is None:
            raise CatalogError(
                f"Reading {path.relative_to(self.root)} requires Python 3.11 or newer."
            )
        try:
            with path.open("rb") as stream:
                descriptor = tomllib.load(stream)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise CatalogError(f"Invalid platform descriptor {path}: {exc}") from exc
        if descriptor.get("schema_version") != self.DESCRIPTOR_VERSION:
            raise CatalogError(
                f"Unsupported schema_version in platform descriptor {path}."
            )
        if descriptor.get("component_id") != name:
            raise CatalogError(
                f"Platform descriptor {path} must declare component_id = {name!r}."
            )

        def validate_config_path(value, attribute):
            if not isinstance(value, str):
                raise CatalogError(
                    f"Platform descriptor {path} needs a string {attribute}."
                )
            candidate = PurePosixPath(value)
            if candidate.is_absolute() or ".." in candidate.parts:
                raise CatalogError(
                    f"Platform descriptor {path} has an unsafe {attribute}."
                )
            if not value.startswith("config/"):
                raise CatalogError(
                    f"Platform descriptor {path} {attribute} must be under config/."
                )
            return value

        validate_config_path(descriptor.get("config_file"), "config_file")

        setting_keys = descriptor.get("setting_keys", [])
        if not isinstance(setting_keys, list) or any(
            not isinstance(key, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]*", key)
            for key in setting_keys
        ):
            raise CatalogError(f"Platform descriptor {path} has invalid setting_keys.")
        if len(setting_keys) != len(set(setting_keys)):
            raise CatalogError(f"Platform descriptor {path} repeats a setting key.")

        shared_groups = descriptor.get("shared_groups", [])
        if not isinstance(shared_groups, list) or any(
            not isinstance(group, str) or not re.fullmatch(r"[a-z][a-z0-9-]*", group)
            for group in shared_groups
        ):
            raise CatalogError(f"Platform descriptor {path} has invalid shared_groups.")
        if len(shared_groups) != len(set(shared_groups)):
            raise CatalogError(f"Platform descriptor {path} repeats a shared group.")

        shared_settings = descriptor.get("shared_settings", [])
        if not isinstance(shared_settings, list):
            raise CatalogError(f"Platform descriptor {path} shared_settings must be a list.")
        seen_shared_settings = set()
        for setting in shared_settings:
            if not isinstance(setting, dict):
                raise CatalogError(f"Platform descriptor {path} has an invalid shared setting.")
            key = setting.get("name")
            group = setting.get("shared_group")
            if (
                not isinstance(key, str)
                or not re.fullmatch(r"[A-Z][A-Z0-9_]*", key)
                or key in setting_keys
                or key in seen_shared_settings
            ):
                raise CatalogError(
                    f"Platform descriptor {path} has an invalid or duplicate shared setting key."
                )
            if not isinstance(group, str) or group not in shared_groups:
                raise CatalogError(
                    f"Shared setting {key!r} in {path} needs a declared shared_group."
                )
            seen_shared_settings.add(key)
            validate_config_path(setting.get("owner_file"), f"owner_file for {key}")

        setup = descriptor.get("setup", {})
        if not isinstance(setup, dict):
            raise CatalogError(f"Platform descriptor {path} has an invalid [setup] section.")
        fields = setup.get("fields", [])
        if not isinstance(fields, list):
            raise CatalogError(f"Platform descriptor {path} setup.fields must be an array.")
        seen = set()
        for field in fields:
            if not isinstance(field, dict):
                raise CatalogError(f"Platform descriptor {path} has an invalid setup field.")
            key = field.get("name")
            kind = field.get("kind")
            group = field.get("shared_group")
            if (
                not isinstance(key, str)
                or not re.fullmatch(r"[A-Z][A-Z0-9_]*", key)
                or key not in setting_keys
                or key in seen
            ):
                raise CatalogError(
                    f"Platform setup field {key!r} in {path} must be a unique owned setting key."
                )
            seen.add(key)
            if (
                not isinstance(kind, str)
                or kind not in ServiceCatalog.SETUP_FIELD_KINDS
            ):
                raise CatalogError(
                    f"Platform setup field {key!r} in {path} has unsupported kind {kind!r}."
                )
            if kind == "defaulted-choice" and not isinstance(field.get("default"), str):
                raise CatalogError(
                    f"Platform setup field {key!r} in {path} needs a string default."
                )
            if not isinstance(group, str) or group not in shared_groups:
                raise CatalogError(
                    f"Platform setup field {key!r} in {path} needs a declared shared_group."
                )
            if kind == "generated-secret":
                generator = field.get("generator", "url-safe")
                if (
                    not isinstance(generator, str)
                    or generator not in ServiceCatalog.BUILTIN_GENERATORS
                ):
                    raise CatalogError(
                        f"Platform setup field {key!r} in {path} has unsupported generator."
                    )
            for attribute in ("default", "note", "change_notice", "generated_notice"):
                value = field.get(attribute)
                if value is not None and not isinstance(value, str):
                    raise CatalogError(
                        f"Platform setup field {key!r} in {path} has invalid {attribute}."
                    )
            length = field.get("length")
            if length is not None and (
                not isinstance(length, int) or isinstance(length, bool) or length < 1
            ):
                raise CatalogError(
                    f"Platform setup field {key!r} in {path} has invalid length."
                )
        return PlatformComponentDefinition(
            name=name,
            directory=path.parent,
            descriptor_file=path,
            descriptor=MappingProxyType(descriptor),
        )


class ServiceCatalog:
    """Read-only catalog derived from services/<name>/compose.yml."""

    DESCRIPTOR_NAME = "opendock.toml"
    DESCRIPTOR_VERSION = 1
    CAPABILITY_API_VERSION = 1
    SETUP_FIELD_KINDS = frozenset({
        "required-user", "defaulted-choice", "initial-credential",
        "secret-user", "generated-secret",
    })
    # Add a capability here only when its handler contract and common dispatcher
    # are implemented. Unknown declarations must fail instead of being ignored.
    CAPABILITIES = frozenset({
        "runtime_environment", "prepare", "plan_secrets", "generate_secrets",
        "validate_config",
    })
    BUILTIN_GENERATORS = frozenset({"url-safe", "alphanumeric", "hex"})

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.platform = PlatformCatalog(self.root)
        self.shared_setup_groups = frozenset(
            group
            for component in self.platform.components
            for group in component.shared_groups
        )
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
        if "plan_secrets" in capabilities and "generate_secrets" not in capabilities:
            raise CatalogError(
                f"Service descriptor {path} declares plan_secrets without generate_secrets."
            )

        commands = descriptor.get("commands", [])
        if not isinstance(commands, list):
            raise CatalogError(f"Service descriptor {path} commands must be an array of tables.")
        seen_commands = set()
        for command in commands:
            if not isinstance(command, dict):
                raise CatalogError(f"Service descriptor {path} contains an invalid command entry.")
            name = command.get("name")
            if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
                raise CatalogError(f"Service descriptor {path} has an invalid command name.")
            if name in seen_commands:
                raise CatalogError(f"Service descriptor {path} repeats command {name!r}.")
            seen_commands.add(name)
            summary = command.get("summary")
            if not isinstance(summary, str) or not summary.strip():
                raise CatalogError(
                    f"Service command {name!r} in {path} needs a non-empty summary."
                )
            details = command.get("details")
            if details is not None and not isinstance(details, str):
                raise CatalogError(
                    f"Service command {name!r} in {path} has non-string details."
                )
            examples = command.get("examples", [])
            if not isinstance(examples, list) or any(
                not isinstance(example, str) or not example.strip() for example in examples
            ):
                raise CatalogError(
                    f"Service command {name!r} in {path} examples must be a string list."
                )
            executable = path.parent / "commands" / name
            if not executable.is_file() or not os.access(executable, os.X_OK):
                raise CatalogError(
                    f"Service command {name!r} in {path} has no executable "
                    f"services/{service_id}/commands/{name} file."
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
        unknown_setup_dependencies = sorted(set(setup_dependencies) - self.shared_setup_groups)
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
            for attribute in ("default", "note", "change_notice", "generated_notice"):
                value = field.get(attribute)
                if value is not None and not isinstance(value, str):
                    raise CatalogError(
                        f"Setup field {name!r} in {path} has a non-string {attribute}."
                    )
            if "required" in field and type(field["required"]) is not bool:
                raise CatalogError(
                    f"Setup field {name!r} in {path} has a non-boolean required flag."
                )
            if kind == "defaulted-choice" and not isinstance(field.get("default"), str):
                raise CatalogError(
                    f"Setup field {name!r} in {path} needs a string default."
                )
            generator = field.get("generator", "url-safe")
            if kind == "generated-secret":
                if not isinstance(generator, str) or not generator.strip():
                    raise CatalogError(
                        f"Setup field {name!r} in {path} has an invalid generator declaration."
                    )
                if (generator not in self.BUILTIN_GENERATORS
                        and "generate_secrets" not in capabilities):
                    raise CatalogError(
                        f"Setup field {name!r} in {path} requires the generate_secrets capability."
                    )
            elif "generator" in field:
                raise CatalogError(
                    f"Setup field {name!r} in {path} may set generator only for generated-secret fields."
                )
            if "length" in field and (
                type(field["length"]) is not int or field["length"] < 1
            ):
                raise CatalogError(
                    f"Setup field {name!r} in {path} has an invalid generator length."
                )

        removal = descriptor.get("removal", {})
        if not isinstance(removal, dict):
            raise CatalogError(f"Service descriptor {path} has an invalid [removal] section.")
        unknown_removal = sorted(
            set(removal) - {"data_paths", "extra_images", "orphan_containers"}
        )
        if unknown_removal:
            raise CatalogError(
                f"Service descriptor {path} has unsupported removal fields: "
                + ", ".join(unknown_removal)
            )
        data_paths = removal.get("data_paths", [])
        extra_images = removal.get("extra_images", [])
        orphan_containers = removal.get("orphan_containers", [])
        for key, entries in (("data_paths", data_paths), ("extra_images", extra_images)):
            if not isinstance(entries, list) or any(
                not isinstance(item, str) or not item.strip() for item in entries
            ):
                raise CatalogError(
                    f"Service descriptor {path} removal.{key} must be a string list."
                )
            if len(entries) != len(set(entries)):
                raise CatalogError(
                    f"Service descriptor {path} removal.{key} contains duplicates."
                )
        for item in data_paths:
            relative = PurePosixPath(item)
            if relative.is_absolute() or ".." in relative.parts or not relative.parts:
                raise CatalogError(
                    f"Service descriptor {path} has unsafe removal data path {item!r}."
                )
        if not isinstance(orphan_containers, list):
            raise CatalogError(
                f"Service descriptor {path} removal.orphan_containers must be an array of tables."
            )
        seen_orphans = set()
        for item in orphan_containers:
            if not isinstance(item, dict):
                raise CatalogError(
                    f"Service descriptor {path} has an invalid removal orphan container."
                )
            label = item.get("label")
            owned_path = item.get("path")
            if not isinstance(label, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", label):
                raise CatalogError(
                    f"Service descriptor {path} has an invalid orphan container label."
                )
            if label in seen_orphans:
                raise CatalogError(
                    f"Service descriptor {path} repeats orphan container label {label!r}."
                )
            seen_orphans.add(label)
            if owned_path not in data_paths:
                raise CatalogError(
                    f"Orphan container {label!r} in {path} must use a declared removal data path."
                )
        return descriptor


def service_names(root: Path) -> tuple[str, ...]:
    """Return discovered service names in stable sorted order."""
    return ServiceCatalog(root).names
