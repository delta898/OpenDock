"""Hermes-specific capabilities for the OpenDock service contract."""

import json
import re
from pathlib import Path

from opendock_capabilities import PreparationResult, RuntimeContext, ServiceContext


OPENDOCK_CAPABILITY_API_VERSION = 1


def runtime_environment(context: RuntimeContext) -> dict[str, str]:
    """Set host-dependent values needed by Hermes' nested Docker sandbox."""
    sandbox_dir = context.service.directory / "data" / "sandboxes"
    socket_path = Path(context.docker_socket)
    socket_gid = str(socket_path.stat().st_gid) if socket_path.exists() else "0"
    return {
        "DOCKER_SOCKET_GID": socket_gid,
        "HERMES_SANDBOX_DIR": str(sandbox_dir),
    }


def _configured_model(context: ServiceContext) -> bool | None:
    try:
        output = context.compose.run(
            "run", "--rm", "--no-deps", "hermes", "config", "get", "model",
            capture=True,
        )
    except Exception:
        return None

    if not output or not output.strip():
        return False
    default = re.search(r"(?m)^\s*default:\s*(.*?)\s*$", output)
    if default:
        value = default.group(1).strip().strip("\"'")
        return bool(value) and value.lower() not in {"null", "none", "unset"}
    try:
        value = json.loads(output)
    except json.JSONDecodeError:
        return None

    def configured(item):
        if isinstance(item, str):
            return bool(item.strip()) and item.strip().lower() not in {"null", "none", "unset"}
        if isinstance(item, dict):
            if "default" in item:
                return configured(item["default"])
            if "model" in item:
                return configured(item["model"])
        if isinstance(item, list):
            return any(configured(child) for child in item)
        return False

    return configured(value)


def prepare(context: ServiceContext) -> PreparationResult:
    """Run Hermes' first-use model onboarding once, without resetting state."""
    if context.compose.named_volume_exists("hermes_data"):
        context.report("checking onboarding status")
        model_ready = _configured_model(context)
        if model_ready is None:
            raise RuntimeError(
                "Could not inspect Hermes' model configuration. "
                "Run './opendock setup hermes' to review its configuration, then retry."
            )
    else:
        context.report("no data volume found; first-run onboarding required")
        model_ready = False

    if model_ready:
        return PreparationResult("not_needed", "onboarding already complete; skipping")

    context.report("first-run onboarding")
    context.compose.run("run", "--rm", "hermes", "setup")
    if _configured_model(context) is not True:
        raise RuntimeError(
            "Hermes onboarding did not configure a default model. "
            "Run './opendock setup hermes' to complete the setup prompts, then retry."
        )
    return PreparationResult("completed", "onboarding completed")
