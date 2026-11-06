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
class SecretPlanningContext:
    """Read-only inputs for expanding related generated-secret fields."""

    service: ServiceDefinition
    selected_keys: frozenset[str]
    settings: Mapping[str, str]


@dataclass(frozen=True)
class SecretPlan:
    """Service-owned generated-secret keys that must be created together."""

    keys: frozenset[str] = frozenset()


@dataclass(frozen=True)
class SecretGenerationContext:
    """Scoped inputs and tools for generating one service's secrets."""

    service: ServiceDefinition
    requested_keys: frozenset[str]
    settings: Mapping[str, str]
    run_image: Callable[..., str]
    report: Callable[[str], None]


@dataclass(frozen=True)
class ValidationContext:
    """Read-only service configuration and tracked examples for validation."""

    service: ServiceDefinition
    settings: Mapping[str, str]
    examples: Mapping[str, str]


@dataclass(frozen=True)
class ValidationResult:
    """User-safe configuration problems returned by a service validator."""

    issues: tuple[str, ...] = ()


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
CAPABILITY_HANDLERS = {
    "runtime_environment": "runtime_environment",
    "prepare": "prepare",
    "post_start": "post_start",
    "plan_secrets": "plan_secrets",
    "generate_secrets": "generate_secrets",
    "validate_config": "validate_config",
}


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
    missing = [
        capability for capability in service.capabilities
        if not callable(getattr(module, CAPABILITY_HANDLERS[capability], None))
    ]
    if missing:
        sys.modules.pop(module_name, None)
        raise CapabilityError(
            f"Service {service.name!r} declares capabilities without handlers: "
            + ", ".join(sorted(missing))
        )
    _MODULES[module_name] = module
    return module


def has_capability(service: ServiceDefinition, name: str) -> bool:
    return name in service.capabilities


def validate_service_capabilities(service: ServiceDefinition) -> None:
    """Preflight declared handlers before a workflow changes service state."""
    if service.capabilities:
        _module_for(service)


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
    if not isinstance(result.message, str):
        raise CapabilityError(
            f"Service {service.name!r} prepare returned a non-string message."
        )
    return result


def post_start(context: ServiceContext) -> None:
    """Call a declared action after Compose starts, before route publication."""
    service = context.service
    if not has_capability(service, "post_start"):
        return
    module = _module_for(service)
    handler = getattr(module, "post_start", None)
    if not callable(handler):
        raise CapabilityError(
            f"Service {service.name!r} declares post_start but does not implement it."
        )
    try:
        result = handler(context)
    except CapabilityError:
        raise
    except Exception as exc:
        raise CapabilityError(
            f"Service {service.name!r} post-start operation failed: {exc}"
        ) from exc
    if result is not None:
        raise CapabilityError(
            f"Service {service.name!r} post_start must return None."
        )


def plan_secrets(context: SecretPlanningContext) -> SecretPlan:
    """Let a service expand missing keys into a consistent secret bundle."""
    service = context.service
    if not has_capability(service, "plan_secrets"):
        return SecretPlan()
    module = _module_for(service)
    handler = getattr(module, "plan_secrets", None)
    if not callable(handler):
        raise CapabilityError(
            f"Service {service.name!r} declares plan_secrets but does not implement it."
        )
    try:
        result = handler(context)
    except Exception as exc:
        raise CapabilityError(
            f"Service {service.name!r} could not plan secret generation: {exc}"
        ) from exc
    if not isinstance(result, SecretPlan):
        raise CapabilityError(f"Service {service.name!r} plan_secrets must return SecretPlan.")
    if not isinstance(result.keys, frozenset) or any(
        not isinstance(key, str) for key in result.keys
    ):
        raise CapabilityError(f"Service {service.name!r} returned invalid secret keys.")
    unknown = result.keys - context.selected_keys
    if unknown:
        raise CapabilityError(
            f"Service {service.name!r} requested undeclared secret keys: "
            + ", ".join(sorted(unknown))
        )
    return result


def generate_secrets(context: SecretGenerationContext) -> Mapping[str, str]:
    """Generate the exact service-owned secret set requested by the core."""
    service = context.service
    if not has_capability(service, "generate_secrets"):
        raise CapabilityError(
            f"Service {service.name!r} has no generate_secrets capability."
        )
    module = _module_for(service)
    handler = getattr(module, "generate_secrets", None)
    if not callable(handler):
        raise CapabilityError(
            f"Service {service.name!r} declares generate_secrets but does not implement it."
        )
    try:
        result = handler(context)
    except Exception as exc:
        raise CapabilityError(
            f"Service {service.name!r} secret generation failed: {exc}"
        ) from exc
    if not isinstance(result, Mapping) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in result.items()
    ):
        raise CapabilityError(f"Service {service.name!r} returned invalid secret values.")
    if set(result) != context.requested_keys:
        raise CapabilityError(
            f"Service {service.name!r} did not return the requested secret set."
        )
    return MappingProxyType(dict(result))


def validate_config(context: ValidationContext) -> ValidationResult:
    """Call a service validator and return user-safe issues for common output."""
    service = context.service
    if not has_capability(service, "validate_config"):
        return ValidationResult()
    module = _module_for(service)
    handler = getattr(module, "validate_config", None)
    if not callable(handler):
        raise CapabilityError(
            f"Service {service.name!r} declares validate_config but does not implement it."
        )
    try:
        result = handler(context)
    except Exception as exc:
        raise CapabilityError(
            f"Service {service.name!r} configuration validation failed: {exc}"
        ) from exc
    if (
        not isinstance(result, ValidationResult)
        or not isinstance(result.issues, tuple)
        or any(not isinstance(issue, str) for issue in result.issues)
    ):
        raise CapabilityError(
            f"Service {service.name!r} validate_config must return ValidationResult."
        )
    return result
