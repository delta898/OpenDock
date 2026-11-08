#!/usr/bin/env python3
"""Create and manage isolated local service integration test checkouts."""

import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import zipfile

try:
    import tomllib
except ModuleNotFoundError:
    tomllib = None

from opendock_root import resolve_root


SOURCE_ROOT = resolve_root(__file__)
SESSION_NAME = "session.json"


def _run(args, *, root=None, env=None, capture=False):
    result = subprocess.run(
        [str(item) for item in args], cwd=root or SOURCE_ROOT,
        env=env, check=False, text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(detail or f"Command failed: {args[0]}")
    return result.stdout.strip() if capture else ""


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _copy_checkout(destination: Path):
    result = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard", "-z"], cwd=SOURCE_ROOT,
        stdout=subprocess.PIPE, check=True,
    )
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        relative = Path(os.fsdecode(raw))
        source = SOURCE_ROOT / relative
        target = destination / relative
        # Python bytecode is machine-local runtime output, not checkout source.
        if "__pycache__" in relative.parts or relative.suffix == ".pyc":
            continue
        if not source.is_file() or source.is_symlink():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _write_session(root: Path, service: str, hostname: str, suffix: str, port: int):
    directory = root / "config" / "local-test"
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "created_at": int(time.time()),
        "source_root": str(SOURCE_ROOT),
        "runtime_root": str(root),
        "service_id": service,
        "hostname": hostname,
        "compose_suffix": suffix,
        "http_port": port,
        "compose_projects": [compose_project_with_suffix(suffix, name)
                             for name in ("infra", "gateway", service)],
        "host_docker_socket": False,
    }
    manifest["runtime_root"] = str(root.resolve())
    path = directory / SESSION_NAME
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    os.chmod(path, 0o600)
    return manifest


def compose_project_with_suffix(suffix: str, target: str) -> str:
    base = target.lower().replace("_", "-")
    return f"od-{suffix[:20]}-{base}"[:63].rstrip("-")


def _seed_config(root: Path, hostname: str, http_port: int):
    config = root / "config"
    files = [
        config / "core.env.default",
        config / "infra.env.default",
        config / "gateway.env.default",
    ]
    for source in files:
        target = source.with_name(source.name.removesuffix(".default"))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    core = config / "core.env"
    lines = [line for line in core.read_text().splitlines() if not line.startswith("STACK_DOMAIN=")]
    lines.insert(1, f"STACK_DOMAIN={'.'.join(hostname.split('.')[1:])}")
    core.write_text("\n".join(lines) + "\n")
    gateway = config / "gateway.env"
    lines = [line for line in gateway.read_text().splitlines()
             if not line.startswith(("HTTP_PORT=", "HTTPS_PORT="))]
    lines.extend([f"HTTP_PORT=127.0.0.1:{http_port}", "HTTPS_PORT=127.0.0.1:0"])
    gateway.write_text("\n".join(lines) + "\n")
    for path in (core, config / "infra.env", gateway):
        os.chmod(path, 0o600)


def _session(root: Path):
    expected_parent = (Path(tempfile.gettempdir()) / "opendock-local-tests").resolve()
    root = root.resolve()
    if root.parent != expected_parent:
        raise RuntimeError(
            f"Refusing to operate outside the local test directory: {expected_parent}"
        )
    path = root / "config" / "local-test" / SESSION_NAME
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"No local test session in {root}")
    data = json.loads(path.read_text())
    try:
        manifest_root = Path(data.get("runtime_root", "")).resolve()
    except (OSError, TypeError, ValueError):
        manifest_root = None
    if data.get("schema_version") != 1 or manifest_root != root:
        raise RuntimeError("Invalid local test session manifest.")
    suffix = data.get("compose_suffix")
    service = data.get("service_id")
    if (not isinstance(suffix, str) or not re.fullmatch(r"[a-f0-9]+", suffix)
            or not isinstance(service, str) or not re.fullmatch(r"[a-z][a-z0-9-]*", service)):
        raise RuntimeError("Invalid service or namespace in local test session manifest.")
    expected_projects = [compose_project_with_suffix(suffix, name)
                         for name in ("infra", "gateway", service)]
    if data.get("compose_projects") != expected_projects:
        raise RuntimeError("Invalid Compose projects in local test session manifest.")
    return data


def start(package: Path, hostname: str, *, allow_host_docker_socket=False):
    package = package.expanduser()
    if package.is_symlink() or not package.is_file() or package.suffix.lower() != ".zip":
        raise RuntimeError("Pass a regular local package .zip file.")
    package = package.resolve()
    hostname = hostname.rstrip(".").lower()
    labels = hostname.split(".")
    if (len(labels) < 2 or labels[-1] != "test"
            or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                   for label in labels)):
        raise RuntimeError("Local test hostname must end in .test, for example app.local.test.")
    if tomllib is None:
        raise RuntimeError("Python 3.11 or newer is required to read the package descriptor.")
    try:
        with zipfile.ZipFile(package) as archive:
            descriptors = [item for item in archive.infolist()
                           if item.filename == "opendock.toml"]
            if len(descriptors) != 1:
                raise RuntimeError("Package must contain exactly one root opendock.toml.")
            descriptor = tomllib.loads(archive.read(descriptors[0]).decode("utf-8"))
    except (OSError, UnicodeDecodeError, zipfile.BadZipFile, tomllib.TOMLDecodeError) as exc:
        raise RuntimeError(f"Could not read local package descriptor: {exc}") from exc
    service = descriptor.get("service_id")
    if not isinstance(service, str) or not re.fullmatch(r"[a-z][a-z0-9-]*", service):
        raise RuntimeError("Package descriptor has an invalid service_id.")
    try:
        with zipfile.ZipFile(package) as archive:
            compose_text = archive.read("compose.yml").decode("utf-8")
    except (KeyError, UnicodeDecodeError, OSError, zipfile.BadZipFile) as exc:
        raise RuntimeError(f"Could not read service Compose definition: {exc}") from exc
    socket_requested = "/var/run/docker.sock" in compose_text or "DOCKER_SOCKET" in compose_text
    if socket_requested and not allow_host_docker_socket:
        raise RuntimeError(
            "This package requests the host Docker socket. It can control Docker resources "
            "outside the test namespace. Rerun with --allow-host-docker-socket only on a "
            "disposable Docker host, or test without this capability."
        )
    docker = subprocess.run(
        ["docker", "info"], stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE, check=False, text=True,
    )
    if docker.returncode:
        detail = (docker.stderr or "").strip()
        raise RuntimeError(
            "Docker daemon is unavailable; no disposable test environment was created."
            + (f" {detail}" if detail else "")
        )
    suffix = secrets.token_hex(5)
    if socket_requested and allow_host_docker_socket:
        print(
            "WARNING: host Docker socket access is enabled. This service can manage "
            "containers and volumes outside this test environment.",
            file=sys.stderr,
        )
    test_base = Path(tempfile.gettempdir()) / "opendock-local-tests"
    test_base.mkdir(parents=True, exist_ok=True)
    root = test_base / suffix
    root.mkdir(mode=0o700)
    try:
        _copy_checkout(root)
        port = _free_port()
        manifest = _write_session(root, service, hostname, suffix, port)
        manifest["host_docker_socket"] = socket_requested
        session_path = root / "config" / "local-test" / SESSION_NAME
        session_path.write_text(json.dumps(manifest, indent=2) + "\n")
        os.chmod(session_path, 0o600)
        _seed_config(root, hostname, port)
        env = os.environ.copy()
        env.update({
            "OPENDOCK_ROOT": str(root),
            "OPENDOCK_LOCAL_TEST": "1",
            "OPENDOCK_COMPOSE_SUFFIX": suffix,
            "OPENDOCK_LOCAL_TEST_HOSTNAME": hostname,
            "OPENDOCK_LOCAL_TEST_SERVICE": service,
        })
        if socket_requested:
            env["OPENDOCK_ALLOW_HOST_DOCKER_SOCKET"] = "1"
        print("==> local-test: install service package", flush=True)
        _run([root / "opendock", "install", "--local-file", package,
              "--environment", "dev"],
             root=root, env=env)
        # Route resolution injects this session's hostname and service ID. A
        # separate route add would see that synthetic route as a duplicate.
        print("==> local-test: configure service", flush=True)
        _run([root / "opendock", "setup", service], root=root, env=env)
        print("==> local-test: launch service through gateway", flush=True)
        _run([root / "opendock", "launch", hostname], root=root, env=env)
        print("Local integration test is running.")
        print(f"Service: {service}")
        print(f"Runtime root: {root}")
        print(f"URL: http://{hostname}:{port}")
        print("Use this curl command without editing /etc/hosts:")
        print(f"  curl --resolve {hostname}:{port}:127.0.0.1 http://{hostname}:{port}/")
        print("To use a browser hostname, add this line to /etc/hosts:")
        print(f"  127.0.0.1 {hostname}")
        print("When finished:")
        print(f"  {root / 'opendock'} local-test stop {root}")
        print(f"  {root / 'opendock'} local-test clean {root}")
        if socket_requested:
            print("WARNING: this test service can control the host Docker daemon.")
    except Exception:
        manifest_path = root / "config" / "local-test" / SESSION_NAME
        if not manifest_path.is_file():
            shutil.rmtree(root, ignore_errors=True)
        else:
            try:
                stop(root, clean=True)
            except Exception as cleanup_error:
                print(f"Test failed; cleanup also failed: {cleanup_error}", file=sys.stderr)
                print(f"Preserved test root for recovery: {root}", file=sys.stderr)
        raise
    return manifest


def status(root: Path):
    root = root.expanduser().resolve()
    data = _session(root)
    print(json.dumps(data, indent=2))


def stop(root: Path, *, clean=False):
    root = root.expanduser().resolve()
    data = _session(root)
    env = os.environ.copy()
    env.update({
        "OPENDOCK_ROOT": str(root),
        "OPENDOCK_LOCAL_TEST": "1",
        "OPENDOCK_COMPOSE_SUFFIX": data["compose_suffix"],
        "OPENDOCK_LOCAL_TEST_HOSTNAME": data["hostname"],
        "OPENDOCK_LOCAL_TEST_SERVICE": data["service_id"],
    })
    if data.get("host_docker_socket"):
        env["OPENDOCK_ALLOW_HOST_DOCKER_SOCKET"] = "1"
    service_releases = root / "services" / "extensions" / data["service_id"] / "releases"
    installed = service_releases.is_dir() and any(service_releases.glob("*/compose.yml"))
    targets = ((data["service_id"],) if installed else ()) + ("gateway", "infra")
    for target in targets:
        result = subprocess.run(
            [sys.executable, root / "opendock", "down", target],
            cwd=root, env=env, text=True, check=False,
        )
        if result.returncode:
            raise RuntimeError(f"Could not stop isolated Compose project {target}.")
    if clean:
        for project in data["compose_projects"]:
            volumes = _run(
                ["docker", "volume", "ls", "--filter",
                 f"label=com.docker.compose.project={project}", "--format", "{{.Name}}"],
                env=env, capture=True,
            ).splitlines()
            if volumes:
                _run(["docker", "volume", "rm", *volumes], env=env)
        network = f"od-{data['compose_suffix']}-shared-net"
        result = subprocess.run(
            ["docker", "network", "inspect", network], env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
        if result.returncode == 0:
            _run(["docker", "network", "rm", network], env=env)
        shutil.rmtree(root)
        print(f"Removed disposable OpenDock checkout: {root}")
    else:
        print(f"Stopped test containers for {root}. Run clean to remove its private files.")


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"-h", "--help"}:
        print("Usage: opendock local-test start <package.zip> --domain <name>.test "
              "[--allow-host-docker-socket]\n"
              "       opendock local-test status <runtime-root>\n"
              "       opendock local-test stop <runtime-root>\n"
              "       opendock local-test clean <runtime-root>")
        return 0 if args else 2
    command = args.pop(0)
    try:
        if command == "start" and len(args) in (3, 4) and args[1] == "--domain":
            allow_socket = len(args) == 4 and args[3] == "--allow-host-docker-socket"
            if len(args) == 4 and not allow_socket:
                raise RuntimeError("Unknown local-test start option.")
            start(Path(args[0]), args[2], allow_host_docker_socket=allow_socket)
        elif command == "status" and len(args) == 1:
            status(Path(args[0]))
        elif command in {"stop", "clean"} and len(args) == 1:
            stop(Path(args[0]), clean=command == "clean")
        else:
            raise RuntimeError("Invalid local-test arguments.")
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"OpenDock local-test: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
