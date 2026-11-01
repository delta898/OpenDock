#!/usr/bin/env python3
import os
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SERVICES_DIR = ROOT_DIR / "services"


def service_dir(name):
    return SERVICES_DIR / name


def command_dir(name):
    return service_dir(name) / "commands"


def is_service(name):
    return (service_dir(name) / "compose.yml").is_file()


def command_files(name):
    directory = command_dir(name)
    if not directory.is_dir():
        return []

    return sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and not path.name.startswith(".") and os.access(path, os.X_OK)
    )


def print_usage():
    print("Usage: ./opendock service <service> [command]")
    print()
    print("Examples:")
    print("  ./opendock service wordpress")
    print("  ./opendock service wordpress multisite")


def list_commands(target):
    commands = command_files(target)
    if not commands:
        print(f"No service-specific commands for: {target}")
        return 0

    print(f"Commands for {target}:")
    for path in commands:
        print(f"  {path.name}")
    return 0


def main():
    target = sys.argv[1].strip() if len(sys.argv) > 1 else ""
    command = sys.argv[2].strip() if len(sys.argv) > 2 else ""
    extra_args = sys.argv[3:]

    if not target:
        print_usage()
        return 0

    if target in ("all", "services", "infra", "gateway"):
        print(f"Service-specific commands require an installed service; '{target}' is not one.")
        print_usage()
        return 1

    if not is_service(target):
        print(f"Unknown service or missing compose.yml: {target}")
        return 1

    if not command:
        return list_commands(target)

    script = command_dir(target) / command
    if not script.is_file() or not os.access(script, os.X_OK):
        print(f"Unknown command for {target}: {command}")
        available = command_files(target)
        if available:
            print()
            print(f"Available commands for {target}:")
            for path in available:
                print(f"  {path.name}")
        return 1

    env = os.environ.copy()
    env["OPENDOCK_ROOT"] = str(ROOT_DIR)
    env["OPENDOCK_SERVICE"] = target
    env["OPENDOCK_SERVICE_COMMAND"] = command

    result = subprocess.run([str(script), *extra_args], cwd=ROOT_DIR, env=env)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
