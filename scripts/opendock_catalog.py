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
    def optional_setup_configs(self) -> tuple[str, ...]:
        setup = self.descriptor.get("setup", {})
        return tuple(setup.get("optional_config", ()))

    @property
    def removal(self) -> Mapping[str, object]:
        return self.descriptor.get("removal", {})

    @property
    def storage_mounts(self) -> tuple[Mapping[str, object], ...]:
        storage = self.descriptor.get("storage", {})
        return tuple(storage.get("mounts", ()))

    @property
    def commands(self) -> tuple[Mapping[str, object], ...]:
        return tuple(self.descriptor.get("commands", ()))

    @property
    def routing(self) -> Mapping[str, object]:
        return self.descriptor.get("routing", {})


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
    def always_include_config(self) -> bool:
        return self.descriptor.get("always_include_config", False)

    @property
    def shared_groups(self) -> tuple[str, ...]:
        return tuple(self.descriptor.get("shared_groups", ()))

    @property
    def setup_fields(self) -> tuple[Mapping[str, object], ...]:
        setup = self.descriptor.get("setup", {})
        return tuple(setup.get("fields", ()))

    @property
    def shared_databases(self) -> tuple[Mapping[str, object], ...]:
        return tuple(self.descriptor.get("shared_databases", ()))


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
            for key in component.setting_keys
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
        unknown_component_fields = sorted(
            set(descriptor) - {
                "schema_version", "component_id", "always_include_config", "config_file",
                "setting_keys", "shared_groups", "shared_databases", "setup",
            }
        )
        if unknown_component_fields:
            raise CatalogError(
                f"Platform descriptor {path} has unsupported fields: "
                + ", ".join(unknown_component_fields)
            )
        if "always_include_config" in descriptor and type(
            descriptor["always_include_config"]
        ) is not bool:
            raise CatalogError(
                f"Platform descriptor {path} always_include_config must be a boolean."
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

        shared_databases = descriptor.get("shared_databases", [])
        if not isinstance(shared_databases, list):
            raise CatalogError(f"Platform descriptor {path} shared_databases must be a list.")
        seen_database_groups = set()
        for database in shared_databases:
            if not isinstance(database, dict):
                raise CatalogError(f"Platform descriptor {path} has an invalid shared database.")
            unknown_database_fields = sorted(
                set(database) - {"shared_group", "engine", "adapter", "container"}
            )
            if unknown_database_fields:
                raise CatalogError(
                    f"Platform descriptor {path} has unsupported shared database fields: "
                    + ", ".join(unknown_database_fields)
                )
            group = database.get("shared_group")
            engine = database.get("engine")
            adapter = database.get("adapter")
            container = database.get("container")
            if (
                not isinstance(group, str)
                or group not in shared_groups
                or group in seen_database_groups
            ):
                raise CatalogError(
                    f"Platform descriptor {path} has an invalid shared database group."
                )
            if not isinstance(engine, str) or not re.fullmatch(r"[a-z][a-z0-9_-]*", engine):
                raise CatalogError(
                    f"Platform descriptor {path} has an invalid shared database engine."
                )
            if not isinstance(adapter, str) or not re.fullmatch(
                r"[a-z][a-z0-9_-]*", adapter
            ):
                raise CatalogError(
                    f"Platform descriptor {path} has an invalid shared database adapter."
                )
            adapter_file = path.parent / "adapters" / f"{adapter}.py"
            if not adapter_file.is_file():
                raise CatalogError(
                    f"Platform descriptor {path} references missing database adapter {adapter!r}."
                )
            if not isinstance(container, str) or not re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9_.-]*", container
            ):
                raise CatalogError(
                    f"Platform descriptor {path} has an invalid shared database container."
                )
            seen_database_groups.add(group)

        setup = descriptor.get("setup", {})
        if not isinstance(setup, dict):
            raise CatalogError(f"Platform descriptor {path} has an invalid [setup] section.")
        unknown_setup_fields = sorted(set(setup) - {"fields"})
        if unknown_setup_fields:
            raise CatalogError(
                f"Platform descriptor {path} has unsupported setup fields: "
                + ", ".join(unknown_setup_fields)
            )
        fields = setup.get("fields", [])
        if not isinstance(fields, list):
            raise CatalogError(f"Platform descriptor {path} setup.fields must be an array.")
        seen = set()
        for field in fields:
            if not isinstance(field, dict):
                raise CatalogError(f"Platform descriptor {path} has an invalid setup field.")
            unknown_field_keys = sorted(
                set(field) - {
                    "name", "kind", "default", "note", "change_notice",
                    "generated_notice", "generator", "length", "required", "shared_group",
                }
            )
            if unknown_field_keys:
                raise CatalogError(
                    f"Platform descriptor {path} has unsupported setup field keys: "
                    + ", ".join(unknown_field_keys)
                )
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
        "validate_config", "post_launch",
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
        platform_names = {component.name for component in self.platform.components}
        known = set(self._by_name) | platform_names
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

        unknown_descriptor_fields = sorted(
            set(descriptor) - {
                "schema_version", "service_id", "display_name", "capability_api_version",
                "capabilities", "dependencies", "commands", "setup", "routing", "removal",
                "storage",
            }
        )
        if unknown_descriptor_fields:
            raise CatalogError(
                f"Service descriptor {path} has unsupported fields: "
                + ", ".join(unknown_descriptor_fields)
            )

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

        routing = descriptor.get("routing", {})
        if not isinstance(routing, dict):
            raise CatalogError(f"Service descriptor {path} has invalid [routing] metadata.")
        unknown_routing = sorted(set(routing) - {"subdomain_key", "caddy_handler"})
        if unknown_routing:
            raise CatalogError(
                f"Service descriptor {path} has unsupported routing fields: "
                + ", ".join(unknown_routing)
            )
        if routing:
            subdomain_key = routing.get("subdomain_key")
            caddy_handler = routing.get("caddy_handler")
            if not isinstance(subdomain_key, str) or not re.fullmatch(
                r"[A-Z][A-Z0-9_]*", subdomain_key
            ):
                raise CatalogError(f"Service descriptor {path} has an invalid routing subdomain_key.")
            if not isinstance(caddy_handler, str) or not re.fullmatch(
                r"[a-z][a-z0-9_]*_proxy", caddy_handler
            ):
                raise CatalogError(f"Service descriptor {path} has an invalid routing caddy_handler.")

        commands = descriptor.get("commands", [])
        if not isinstance(commands, list):
            raise CatalogError(f"Service descriptor {path} commands must be an array of tables.")
        seen_commands = set()
        for command in commands:
            if not isinstance(command, dict):
                raise CatalogError(f"Service descriptor {path} contains an invalid command entry.")
            unknown_command_fields = sorted(
                set(command) - {"name", "summary", "details", "examples"}
            )
            if unknown_command_fields:
                raise CatalogError(
                    f"Service descriptor {path} has unsupported command fields: "
                    + ", ".join(unknown_command_fields)
                )
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
        platform_names = {component.name for component in self.platform.components}
        unsupported_dependencies = sorted(set(dependencies) - platform_names)
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
        unknown_setup_fields = sorted(
            set(setup) - {"fields", "dependencies", "optional_config"}
        )
        if unknown_setup_fields:
            raise CatalogError(
                f"Service descriptor {path} has unsupported setup fields: "
                + ", ".join(unknown_setup_fields)
            )
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
        optional_config = setup.get("optional_config", [])
        if (
            not isinstance(optional_config, list)
            or any(
                not isinstance(item, str)
                or not re.fullmatch(r"[a-z][a-z0-9-]*", item)
                for item in optional_config
            )
        ):
            raise CatalogError(
                f"Service descriptor {path} setup.optional_config must be a string list."
            )
        if len(optional_config) != len(set(optional_config)):
            raise CatalogError(
                f"Service descriptor {path} contains duplicate optional setup configs."
            )
        prefix = service_id.replace("-", "_").upper() + "_"
        seen_fields = set()
        for field in setup_fields:
            if not isinstance(field, dict):
                raise CatalogError(f"Service descriptor {path} contains an invalid setup field.")
            unknown_field_keys = sorted(
                set(field) - {
                    "name", "kind", "default", "note", "change_notice",
                    "generated_notice", "required", "generator", "length",
                }
            )
            if unknown_field_keys:
                raise CatalogError(
                    f"Service descriptor {path} has unsupported setup field keys: "
                    + ", ".join(unknown_field_keys)
                )
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

        if routing and routing["subdomain_key"] not in seen_fields:
            raise CatalogError(
                f"Service descriptor {path} routing subdomain_key must be a declared setup field."
            )

        removal = descriptor.get("removal", {})
        if not isinstance(removal, dict):
            raise CatalogError(f"Service descriptor {path} has an invalid [removal] section.")
        unknown_removal = sorted(
            set(removal)
            - {
                "data_paths", "preserve_paths", "config_files",
                "extra_images", "orphan_containers", "shared_database",
            }
        )
        if unknown_removal:
            raise CatalogError(
                f"Service descriptor {path} has unsupported removal fields: "
                + ", ".join(unknown_removal)
            )
        data_paths = removal.get("data_paths", [])
        preserve_paths = removal.get("preserve_paths", [])
        config_files = removal.get("config_files", [])
        extra_images = removal.get("extra_images", [])
        orphan_containers = removal.get("orphan_containers", [])
        shared_database = removal.get("shared_database")
        if shared_database is not None:
            if not isinstance(shared_database, dict):
                raise CatalogError(
                    f"Service descriptor {path} has an invalid removal.shared_database declaration."
                )
            unknown_database_fields = sorted(
                set(shared_database) - {"shared_group", "database_key", "role_key"}
            )
            if unknown_database_fields:
                raise CatalogError(
                    f"Service descriptor {path} has unsupported shared database fields: "
                    + ", ".join(unknown_database_fields)
                )
            group = shared_database.get("shared_group")
            database_key = shared_database.get("database_key")
            role_key = shared_database.get("role_key")
            known_database_groups = {
                item["shared_group"]
                for component in self.platform.components
                for item in component.shared_databases
            }
            if not isinstance(group, str) or group not in setup_dependencies:
                raise CatalogError(
                    f"Service descriptor {path} removal.shared_database must use a declared setup dependency."
                )
            if group not in known_database_groups:
                raise CatalogError(
                    f"Service descriptor {path} references a shared database group without a platform adapter."
                )
            for key_name, key in (("database_key", database_key), ("role_key", role_key)):
                if (
                    not isinstance(key, str)
                    or not re.fullmatch(r"[A-Z][A-Z0-9_]*", key)
                    or not key.startswith(prefix)
                ):
                    raise CatalogError(
                        f"Service descriptor {path} shared database {key_name} must use the {prefix} prefix."
                    )
            if database_key == role_key:
                raise CatalogError(
                    f"Service descriptor {path} must declare different database and role keys."
                )
        for key, entries in (
            ("data_paths", data_paths),
            ("preserve_paths", preserve_paths),
            ("config_files", config_files),
            ("extra_images", extra_images),
        ):
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
        for key, entries in (
            ("data_paths", data_paths),
            ("preserve_paths", preserve_paths),
            ("config_files", config_files),
        ):
            for item in entries:
                relative = PurePosixPath(item)
                if relative.is_absolute() or ".." in relative.parts or not relative.parts:
                    raise CatalogError(
                        f"Service descriptor {path} has unsafe removal {key} path {item!r}."
                    )

        storage = descriptor.get("storage", {})
        if not isinstance(storage, dict):
            raise CatalogError(f"Service descriptor {path} has invalid [storage] metadata.")
        unknown_storage_fields = sorted(set(storage) - {"mounts"})
        if unknown_storage_fields:
            raise CatalogError(
                f"Service descriptor {path} has unsupported storage fields: "
                + ", ".join(unknown_storage_fields)
            )
        mounts = storage.get("mounts", [])
        if not isinstance(mounts, list):
            raise CatalogError(f"Service descriptor {path} storage.mounts must be an array of tables.")
        fields_by_name = {field["name"]: field for field in setup_fields}
        seen_mounts = set()
        seen_mount_keys = set()
        for mount in mounts:
            if not isinstance(mount, dict):
                raise CatalogError(f"Service descriptor {path} contains an invalid storage mount.")
            unknown_mount_fields = sorted(
                set(mount) - {"name", "setting_key", "container_path", "access"}
            )
            if unknown_mount_fields:
                raise CatalogError(
                    f"Service descriptor {path} has unsupported storage mount fields: "
                    + ", ".join(unknown_mount_fields)
                )
            name = mount.get("name")
            setting_key = mount.get("setting_key")
            container_path = mount.get("container_path")
            access = mount.get("access")
            if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_-]*", name):
                raise CatalogError(f"Service descriptor {path} has an invalid storage mount name.")
            if name in seen_mounts:
                raise CatalogError(f"Service descriptor {path} repeats storage mount {name!r}.")
            seen_mounts.add(name)
            if (
                not isinstance(setting_key, str)
                or not setting_key.startswith(prefix)
                or setting_key not in fields_by_name
                or fields_by_name[setting_key].get("kind") != "defaulted-choice"
            ):
                raise CatalogError(
                    f"Storage mount {name!r} in {path} must reference a defaulted service setup field."
                )
            if setting_key in seen_mount_keys:
                raise CatalogError(f"Service descriptor {path} repeats storage setting {setting_key!r}.")
            seen_mount_keys.add(setting_key)
            if (
                not isinstance(container_path, str)
                or not container_path.startswith("/")
                or ".." in PurePosixPath(container_path).parts
            ):
                raise CatalogError(f"Storage mount {name!r} in {path} has an invalid container_path.")
            if access not in ("read-only", "read-write"):
                raise CatalogError(
                    f"Storage mount {name!r} in {path} access must be read-only or read-write."
                )
            default_path = fields_by_name[setting_key].get("default")
            relative_default = PurePosixPath(default_path) if isinstance(default_path, str) else None
            if (
                relative_default is None
                or relative_default.is_absolute()
                or ".." in relative_default.parts
                or relative_default.as_posix().removeprefix("./") not in data_paths
            ):
                raise CatalogError(
                    f"Storage mount {name!r} in {path} must default to a declared removal.data_paths entry."
                )

        if set(data_paths) & set(config_files):
            raise CatalogError(
                f"Service descriptor {path} declares a path as both data and config."
            )
        if set(preserve_paths) & (set(data_paths) | set(config_files)):
            raise CatalogError(
                f"Service descriptor {path} declares a preserved path as removable."
            )
        for preserved in preserve_paths:
            preserved_path = PurePosixPath(preserved)
            if not any(
                preserved_path.is_relative_to(PurePosixPath(data_path))
                for data_path in data_paths
            ):
                raise CatalogError(
                    f"Preserved path {preserved!r} in {path} must be inside a removal data path."
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
            unknown_orphan_fields = sorted(set(item) - {"label", "path"})
            if unknown_orphan_fields:
                raise CatalogError(
                    f"Service descriptor {path} has unsupported orphan container fields: "
                    + ", ".join(unknown_orphan_fields)
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
