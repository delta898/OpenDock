#!/usr/bin/env python3
import os
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SERVICES_DIR = ROOT_DIR / "services"
COMMAND_HELP = {
    ("hermes", "onboard"): {
        "summary": "Open Hermes' interactive first-run setup wizard.",
        "details": (
            "Choose Hermes' model provider and configure its credentials and default model. "
            "A fresh 'launch hermes' runs this automatically; use this command to reopen "
            "the wizard later. It ensures shared infrastructure is running first."
        ),
        "examples": ["./opendock service hermes onboard"],
    },
    ("wordpress", "multisite"): {
        "summary": "Convert WordPress to subdirectory multisite mode.",
        "details": (
            "Uses the configured WordPress hostname and asks for confirmation before "
            "changing WordPress configuration and database behavior. Reverting after "
            "creating sites or content requires a migration. Set YES=1 for automation."
        ),
        "examples": [
            "./opendock service wordpress multisite",
            "YES=1 ./opendock service wordpress multisite",
        ],
    },
    ("supabase", "api-keys"): {
        "summary": "Show the Supabase URL and publishable client key.",
        "details": "Secret keys and legacy service-role values remain hidden.",
        "examples": ["./opendock service supabase api-keys"],
    },
    ("supabase", "functions-secrets"): {
        "summary": "Review names of local Supabase Edge Function secrets.",
        "details": (
            "Creates services/supabase/functions.env from its example when missing, "
            "sets restrictive file permissions, and prints configured names without values."
        ),
        "examples": ["./opendock service supabase functions-secrets"],
    },
}


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
    print("Usage: ./opendock service <service> [command] [arguments]")
    print()
    print("Use --help at either level:")
    print("  ./opendock service <service> --help")
    print("  ./opendock service <service> <command> --help")
    print()
    print("Examples:")
    print("  ./opendock service hermes --help")
    print("  ./opendock service hermes onboard --help")


def print_command_help(target, command):
    command_path = command_dir(target) / command
    if not command_path.is_file() or not os.access(command_path, os.X_OK):
        print(f"Unknown command for {target}: {command}")
        list_commands(target)
        return 1

    info = COMMAND_HELP.get((target, command), {})
    summary = info.get("summary", f"Run the {command} command for {target}.")
    details = info.get("details", "")
    print(f"Usage: ./opendock service {target} {command} [arguments]")
    print()
    print(summary)
    if details:
        print()
        print(details)
    print()
    print("Examples:")
    for example in info.get("examples", [f"./opendock service {target} {command}"]):
        print(f"  {example}")
    print()
    print(f"List all {target} commands with: ./opendock service {target} --help")
    return 0


def list_commands(target):
    commands = command_files(target)
    if not commands:
        print(f"No service-specific commands for: {target}")
        return 0

    print(f"Commands for {target}:")
    for path in commands:
        summary = COMMAND_HELP.get((target, path.name), {}).get("summary")
        print(f"  {path.name:<20} {summary or 'Service-specific command'}")
    return 0


def main():
    target = sys.argv[1].strip() if len(sys.argv) > 1 else ""
    command = sys.argv[2].strip() if len(sys.argv) > 2 else ""
    extra_args = sys.argv[3:]

    if command in ("--help", "-h"):
        if not target:
            print_usage()
            return 0
        if target in ("all", "services", "infra", "gateway") or not is_service(target):
            print(f"Unknown service: {target}")
            return 1
        return list_commands(target)

    if not command:
        return list_commands(target)

    if "--help" in extra_args or "-h" in extra_args:
        return print_command_help(target, command)

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
