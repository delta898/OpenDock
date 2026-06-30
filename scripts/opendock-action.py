#!/usr/bin/env python3
import os
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SERVICES_DIR = ROOT_DIR / "services"


def service_dir(name):
    return SERVICES_DIR / name


def action_dir(name):
    return service_dir(name) / "actions"


def is_service(name):
    return (service_dir(name) / "compose.yml").is_file()


def action_files(name):
    directory = action_dir(name)
    if not directory.is_dir():
        return []

    return sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and not path.name.startswith(".") and os.access(path, os.X_OK)
    )


def print_usage():
    print("Usage: make action <service> [action]")
    print()
    print("Examples:")
    print("  make action wordpress")
    print("  make action wordpress multisite")


def list_actions(target):
    actions = action_files(target)
    if not actions:
        print(f"No actions for service: {target}")
        return 0

    print(f"Actions for {target}:")
    for path in actions:
        print(f"  {path.name}")
    return 0


def main():
    target = sys.argv[1].strip() if len(sys.argv) > 1 else ""
    action = sys.argv[2].strip() if len(sys.argv) > 2 else ""
    extra_args = sys.argv[3:]

    if not target:
        print_usage()
        return 0

    if target in ("all", "services", "infra", "gateway"):
        print(f"Actions are service-specific; '{target}' is not a service target.")
        print_usage()
        return 1

    if not is_service(target):
        print(f"Unknown service or missing compose.yml: {target}")
        return 1

    if not action:
        return list_actions(target)

    script = action_dir(target) / action
    if not script.is_file() or not os.access(script, os.X_OK):
        print(f"Unknown action for {target}: {action}")
        available = action_files(target)
        if available:
            print()
            print(f"Available actions for {target}:")
            for path in available:
                print(f"  {path.name}")
        return 1

    env = os.environ.copy()
    env["OPENDOCK_ROOT"] = str(ROOT_DIR)
    env["OPENDOCK_SERVICE"] = target
    env["OPENDOCK_ACTION"] = action

    result = subprocess.run([str(script), *extra_args], cwd=ROOT_DIR, env=env)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
