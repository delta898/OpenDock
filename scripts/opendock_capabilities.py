#!/usr/bin/env python3
"""Stable, scoped interfaces between common workflows and service code."""

import importlib.util
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType, ModuleType
from typing import Callable, Literal, Mapping

from opendock_catalog import ServiceDefinition


class CapabilityError(ValueError):
    """Raised when a service capability cannot be loaded or run safely."""


@dataclass(frozen=True)
class PreparationResult:
    """Outcome of an idempotent service preparation operation."""

    status: Literal["not_needed", "completed"]
    message: str = ""


@dataclass(frozen=True)
class RuntimeContext:
    """Minimal host context for producing Compose interpolation values."""

    service: ServiceDefinition
    docker_socket: str


@dataclass(frozen=True)
class ComposeOperations:
    """Compose operations scoped to exactly one service project."""

    _run: Callable[..., str | None]
    _volume_exists: Callable[[str], bool]

    def run(self, *args: str, capture: bool = False, quiet: bool = False) -> str | None:
        return self._run(*args, capture=capture, quiet=quiet)

    def named_volume_exists(self, volume: str) -> bool:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", volume):
            raise CapabilityError(f"Invalid Compose volume name: {volume!r}")
        return self._volume_exists(volume)


@dataclass(frozen=True)
class ServiceContext:
    """Narrow inputs and platform operations for one service capability."""

    service: ServiceDefinition
    settings: Mapping[str, str]
    compose: ComposeOperations
    report: Callable[[str], None]


_MODULES: dict[str, ModuleType] = {}


def _module_for(service: ServiceDefinition) -> ModuleType:
    module_name = f"_opendock_service_{service.name.replace('-', '_')}"
    if module_name in _MODULES:
        return _MODULES[module_name]

    path = service.directory / "opendock.py"
    if not path.is_file():
        raise CapabilityError(
            f"Service {service.name!r} declares capabilities but has no {path.name}."
        )

    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise CapabilityError(f"Could not load service capability module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        sys.modules.pop(module_name, None)
        raise CapabilityError(
            f"Could not import capabilities for {service.name}: {exc}"
        ) from exc

    expected = service.descriptor.get("capability_api_version")
    actual = getattr(module, "OPENDOCK_CAPABILITY_API_VERSION", None)
    if actual != expected:
        sys.modules.pop(module_name, None)
        raise CapabilityError(
            f"Service {service.name!r} implements capability API {actual!r}; "
            f"its descriptor requires {expected!r}."
        )
    _MODULES[module_name] = module
    return module


def has_capability(service: ServiceDefinition, name: str) -> bool:
    return name in service.capabilities


def runtime_environment(
    service: ServiceDefinition, *, docker_socket: str
) -> Mapping[str, str]:
    """Call a service's optional runtime environment provider."""
    if not has_capability(service, "runtime_environment"):
        return MappingProxyType({})

    module = _module_for(service)
    handler = getattr(module, "runtime_environment", None)
    if not callable(handler):
        raise CapabilityError(
            f"Service {service.name!r} declares runtime_environment but does not implement it."
        )
    try:
        result = handler(RuntimeContext(
            service=service, docker_socket=docker_socket,
        ))
    except Exception as exc:
        raise CapabilityError(
            f"Service {service.name!r} could not prepare its runtime environment: {exc}"
        ) from exc
    if not isinstance(result, Mapping) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in result.items()
    ):
        raise CapabilityError(
            f"Service {service.name!r} returned an invalid runtime environment."
        )
    return MappingProxyType(dict(result))


def prepare(context: ServiceContext) -> PreparationResult:
    """Call a service's optional idempotent prepare capability."""
    service = context.service
    if not has_capability(service, "prepare"):
        return PreparationResult("not_needed")

    module = _module_for(service)
    handler = getattr(module, "prepare", None)
    if not callable(handler):
        raise CapabilityError(
            f"Service {service.name!r} declares prepare but does not implement it."
        )
    try:
        result = handler(context)
    except CapabilityError:
        raise
    except Exception as exc:
        raise CapabilityError(
            f"Service {service.name!r} preparation failed: {exc}"
        ) from exc
    if not isinstance(result, PreparationResult):
        raise CapabilityError(
            f"Service {service.name!r} prepare must return PreparationResult."
        )
    if result.status not in {"not_needed", "completed"}:
        raise CapabilityError(
            f"Service {service.name!r} returned an unknown preparation status."
        )
    return result
