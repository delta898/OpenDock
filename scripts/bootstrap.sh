#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/delta898/OpenDock"
INSTALL_DIR="${HOME}/OpenDock"
INSTALL_DIR_SET=0
BRANCH="main"
BRANCH_SET=0
REPO_URL_SET=0
INSTALL_OPENDOCK=1
HOST_PLATFORM=""
DOCKER_GROUP_ADDED=0
target_user=""
CLOUDFLARE_ENV_FILE=""

usage() {
	cat <<'USAGE'
Usage:
  bootstrap.sh [options]

Prepare an Ubuntu Linux or macOS host, install the minimal OpenDock runtime,
and optionally configure a Cloudflare Tunnel connector.

Options:
  --install            Install the minimal OpenDock runtime after host preparation (default).
  --no-install         Prepare the host without installing OpenDock.
  --dir <path>         OpenDock root. Default: $HOME/OpenDock
  --repo <url>         OpenDock GitHub repository URL.
  --branch <name>      Git branch to download. Default: main
  --no-cloudflared     Skip Cloudflare Tunnel connector setup.
  -h, --help           Show this help.

Examples:
  curl -fsSL https://raw.githubusercontent.com/delta898/OpenDock/main/scripts/bootstrap.sh | bash
  curl -fsSL https://raw.githubusercontent.com/delta898/OpenDock/main/scripts/bootstrap.sh | bash -s -- --dir "$HOME/opendock"
USAGE
}

log() {
	printf '\n==> %s\n' "$*"
}

warn() {
	printf 'Warning: %s\n' "$*" >&2
}

die() {
	printf 'Error: %s\n' "$*" >&2
	exit 1
}

interrupted() {
	printf '\nBootstrap interrupted. No OpenDock service packages were installed.\n' >&2
	exit 130
}
trap interrupted INT

while [ "$#" -gt 0 ]; do
	case "$1" in
		--install)
			INSTALL_OPENDOCK=1
			shift
			;;
		--no-install)
			INSTALL_OPENDOCK=0
			shift
			;;
		--dir)
			[ "$#" -ge 2 ] || die "--dir requires a path"
			INSTALL_DIR="$2"
			INSTALL_DIR_SET=1
			shift 2
			;;
		--repo)
			[ "$#" -ge 2 ] || die "--repo requires a URL"
			REPO_URL="$2"
			REPO_URL_SET=1
			shift 2
			;;
		--branch)
			[ "$#" -ge 2 ] || die "--branch requires a branch name"
			BRANCH="$2"
			BRANCH_SET=1
			shift 2
			;;
		--no-cloudflared)
			CLOUDFLARED_SETUP=0
			shift
			;;
		-h|--help)
			usage
			exit 0
			;;
		*)
			die "Unknown option: $1"
			;;
	esac
done

CLOUDFLARED_SETUP="${CLOUDFLARED_SETUP:-1}"

need_command() {
	command -v "$1" >/dev/null 2>&1
}

run_sudo() {
	if [ "$(id -u)" -eq 0 ]; then
		"$@"
	else
		sudo "$@"
	fi
}

detect_platform() {
	case "$(uname -s)" in
		Linux)
			HOST_PLATFORM="linux"
			;;
		Darwin)
			HOST_PLATFORM="macos"
			;;
		*)
			die "Unsupported host OS: $(uname -s). OpenDock bootstrap supports Ubuntu Linux and macOS."
			;;
	esac
	log "Detected ${HOST_PLATFORM}"
}

prepare_linux_privileges() {
	need_command apt-get || die "apt-get was not found. This bootstrap currently supports Ubuntu Linux."
	if [ "$(id -u)" -ne 0 ] && ! need_command sudo; then
		die "sudo is required to install Ubuntu host packages."
	fi
	if [ "$(id -u)" -eq 0 ] && [ -n "${SUDO_USER:-}" ] && [ "$INSTALL_DIR_SET" -eq 0 ]; then
		local user_home
		user_home="$(getent passwd "$SUDO_USER" | cut -d: -f6)"
		if [ -n "$user_home" ]; then
			INSTALL_DIR="${user_home}/OpenDock"
		fi
	fi
}

check_linux_os() {
	[ -r /etc/os-release ] || die "Could not read /etc/os-release."
	# shellcheck disable=SC1091
	. /etc/os-release
	[ "${ID:-}" = "ubuntu" ] || die "This bootstrap currently supports Ubuntu 24.04 or newer; found ${PRETTY_NAME:-unknown OS}."
	local major minor
	IFS=. read -r major minor _ <<<"${VERSION_ID:-0}"
	if [ "${major:-0}" -lt 24 ] 2>/dev/null; then
		die "Ubuntu 24.04 or newer is required; found ${VERSION_ID:-unknown}."
	fi
}

install_linux_packages() {
	log "Installing Ubuntu host prerequisites"
	run_sudo apt-get update
	run_sudo apt-get install -y python3 curl ca-certificates

	if need_command docker && docker compose version >/dev/null 2>&1; then
		log "Docker Engine and Compose plugin are already installed"
	else
		run_sudo apt-get install -y docker.io docker-compose-v2
	fi
}

enable_linux_docker() {
	if need_command systemctl; then
		log "Enabling Docker Engine with systemd"
		run_sudo systemctl enable --now docker
	else
		die "systemctl was not found; cannot enable the Ubuntu Docker Engine service."
	fi
}

configure_linux_docker_group() {
	target_user="${SUDO_USER:-${USER:-}}"
	if [ -z "$target_user" ] || [ "$target_user" = "root" ]; then
		warn "Could not identify a non-root login user; skipping docker group setup."
		return
	fi
	if id -nG "$target_user" | tr ' ' '\n' | grep -qx docker; then
		log "${target_user} is already in the docker group"
		return
	fi
	log "Adding ${target_user} to the docker group"
	run_sudo usermod -aG docker "$target_user"
	DOCKER_GROUP_ADDED=1
}

verify_linux_docker() {
	log "Checking Docker Engine and Compose"
	run_sudo docker --version
	run_sudo docker compose version
}

prepare_macos() {
	need_command python3 || die "Python 3.11 or newer is required. Install it, then rerun bootstrap."
	python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' \
		|| die "Python 3.11 or newer is required. Install it, then rerun bootstrap."
	need_command docker || die "A Docker-compatible runtime is required. Install Docker Desktop, start it, and rerun bootstrap. See https://docs.docker.com/desktop/setup/install/mac-install/."

	if ! docker info >/dev/null 2>&1; then
		if [ -d /Applications/Docker.app ] || [ -d "${HOME}/Applications/Docker.app" ]; then
			log "Starting Docker Desktop. Complete its first-run agreement/setup in the app if prompted."
			open -a Docker >/dev/null 2>&1 || true
		else
			die "Docker CLI is installed but no Docker daemon is available. Start your Docker-compatible runtime and rerun bootstrap."
		fi
		local attempt=0
		until docker info >/dev/null 2>&1; do
			attempt=$((attempt + 1))
			if [ "$attempt" -ge 120 ]; then
				die "Docker did not become ready within 10 minutes. Complete Docker Desktop setup and rerun bootstrap."
			fi
			if [ $((attempt % 10)) -eq 0 ]; then
				printf 'Waiting for Docker Desktop (%s/120)...\n' "$attempt"
			fi
			sleep 5
		done
	fi
	docker compose version >/dev/null 2>&1 \
		|| die "Docker Compose v2 is required. Update or configure your Docker-compatible runtime, then rerun bootstrap."
	log "Docker-compatible runtime and Compose are ready"
}

prepare_host() {
	case "$HOST_PLATFORM" in
		linux)
			prepare_linux_privileges
			check_linux_os
			install_linux_packages
			enable_linux_docker
			configure_linux_docker_group
			verify_linux_docker
			;;
		macos)
			prepare_macos
			;;
	esac
}

install_platform_runtime() {
	local runtime_mode="install"
	if [ "$INSTALL_OPENDOCK" -ne 1 ]; then
		return
	fi
	if [ -L "$INSTALL_DIR" ]; then
		die "OpenDock root is a symbolic link: ${INSTALL_DIR}. Choose its real directory with --dir."
	fi
	if [ -e "$INSTALL_DIR" ]; then
		if [ -f "$INSTALL_DIR/opendock" ] && [ -e "$INSTALL_DIR/.git" ]; then
			log "Recognized a Git checkout at ${INSTALL_DIR}; leaving repository files untouched."
			return
		elif [ -f "$INSTALL_DIR/opendock" ] && [ -f "$INSTALL_DIR/.opendock-install" ]; then
			log "Recognized the existing minimal OpenDock installation at ${INSTALL_DIR}"
			runtime_mode="refresh"
		elif [ -f "$INSTALL_DIR/opendock" ] \
			&& [ -d "$INSTALL_DIR/config" ] \
			&& [ -d "$INSTALL_DIR/scripts" ] \
			&& [ -d "$INSTALL_DIR/infra" ] \
			&& [ -d "$INSTALL_DIR/gateway" ]; then
			log "Recognized the existing OpenDock runtime at ${INSTALL_DIR}"
			runtime_mode="refresh"
		elif [ -d "$INSTALL_DIR" ] && [ -z "$(find "$INSTALL_DIR" -mindepth 1 -maxdepth 1 -print -quit)" ]; then
			log "Using the existing empty directory at ${INSTALL_DIR} for the OpenDock runtime."
		else
			die "${INSTALL_DIR} exists but is not a recognizable OpenDock directory. Nothing was changed there. Use --dir for an empty path or an existing OpenDock root."
		fi
	fi
	local repository archive_url archive_file="" extract_root install_stage install_parent
	local local_source_root="" script_path script_root source_kind source_path
	if [ "$REPO_URL_SET" -eq 0 ] && [ "$BRANCH_SET" -eq 0 ] && [ -f "${BASH_SOURCE[0]}" ]; then
		script_path="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
		script_root="$(cd "$(dirname "$script_path")/.." && pwd)"
		if [ -f "$script_root/opendock" ] && [ -f "$script_root/config/core.toml" ] && [ -d "$script_root/scripts" ]; then
			local_source_root="$script_root"
		fi
	fi
	if [ -n "$local_source_root" ]; then
		source_kind="directory"
		source_path="$local_source_root"
		log "Preparing the runtime from the local OpenDock source tree"
	else
		need_command curl || die "curl is required to download the OpenDock runtime."
		repository="${REPO_URL#https://github.com/}"
		repository="${repository%.git}"
		if [ "$repository" = "$REPO_URL" ] || [[ "$repository" == */*/* ]]; then
			die "--repo must be an HTTPS GitHub repository URL such as https://github.com/delta898/OpenDock."
		fi
		archive_url="https://codeload.github.com/${repository}/tar.gz/refs/heads/${BRANCH}"
		archive_file="$(mktemp)"
		source_kind="archive"
		source_path="$archive_file"
	fi
	install_parent="$(dirname "$INSTALL_DIR")"
	mkdir -p "$install_parent"
	extract_root="$(mktemp -d "$install_parent/.opendock-bootstrap.XXXXXX")"
	install_stage="$extract_root/runtime"
	mkdir -p "$install_stage"
	trap 'if [ -n "${archive_file:-}" ]; then rm -f "$archive_file"; fi; rm -rf "${extract_root:-}"' EXIT
	if [ "$source_kind" = "archive" ]; then
		log "Downloading the OpenDock runtime source archive (Git is not required)"
		curl -fsSL "$archive_url" -o "$archive_file"
	fi
	python3 - "$source_kind" "$source_path" "$install_stage" <<'PY'
import sys
import tarfile
from pathlib import Path, PurePosixPath
import shutil
import stat

source_kind, source_path, destination = sys.argv[1:]
destination = Path(destination)
source_path = Path(source_path)
exact = {"opendock", "pyproject.toml", "services/groups.conf", "static-sites/README.md"}

def include(path: PurePosixPath) -> bool:
    name = path.as_posix()
    if name in exact:
        return True
    if name.startswith("scripts/"):
        return path.suffix in {".py", ".sh"}
    if name.startswith("config/"):
        return path.suffix in {".toml", ".json", ".default"}
    if name.startswith("infra/"):
        return name in {"infra/compose.yml", "infra/opendock.toml"} or (
            name.startswith("infra/adapters/") and path.suffix == ".py"
        )
    if name.startswith("gateway/"):
        return name in {"gateway/compose.yml", "gateway/opendock.toml", "gateway/caddy/Caddyfile"} or (
            name.startswith("gateway/caddy/conf.d/") and path.suffix == ".caddy"
        )
    return False

def copy_file(source: Path, relative: PurePosixPath, mode: int) -> None:
    target = destination.joinpath(*relative.parts)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    target.chmod(mode & 0o755 or 0o644)

copied = 0
if source_kind == "directory":
    for source in source_path.rglob("*"):
        if source.is_symlink() or not source.is_file():
            continue
        relative = PurePosixPath(source.relative_to(source_path).as_posix())
        if include(relative):
            copy_file(source, relative, stat.S_IMODE(source.stat().st_mode))
            copied += 1
elif source_kind == "archive":
    with tarfile.open(source_path, "r:gz") as bundle:
        members = bundle.getmembers()
        if not members:
            raise SystemExit("The OpenDock source archive is empty.")
        prefix = members[0].name.split("/", 1)[0]
        for member in members:
            raw = PurePosixPath(member.name)
            if len(raw.parts) < 2 or raw.parts[0] != prefix:
                continue
            relative = PurePosixPath(*raw.parts[1:])
            if relative.is_absolute() or ".." in relative.parts or not include(relative):
                continue
            if not member.isfile():
                continue
            source = bundle.extractfile(member)
            if source is None:
                continue
            target = destination.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            target.chmod(member.mode & 0o755 or 0o644)
            copied += 1
else:
    raise SystemExit("Unsupported OpenDock runtime source.")

if copied < 10:
    raise SystemExit("The source did not contain the expected OpenDock runtime files.")
PY
	chmod 700 "$install_stage/opendock"
	: > "$install_stage/.opendock-install"
	chmod 600 "$install_stage/.opendock-install"
	mkdir -p "$install_stage/services/extensions"
	if [ "$runtime_mode" = "refresh" ]; then
		log "Refreshing runtime files while preserving local configuration and installed services"
		python3 - "$install_stage" "$INSTALL_DIR" "${SUDO_USER:-}" <<'PY'
import os
from pathlib import Path
import pwd
import shutil
import sys

source_root = Path(sys.argv[1])
target_root = Path(sys.argv[2])
sudo_user = sys.argv[3]
owner = pwd.getpwnam(sudo_user) if sudo_user and os.geteuid() == 0 else None
items = sorted(source_root.rglob("*"))

# Validate destinations before writing. Runtime refresh must not follow an
# existing symlink out of the selected OpenDock root.
for source in items:
    target = target_root / source.relative_to(source_root)
    current = target
    while current != target_root:
        if current.is_symlink():
            raise SystemExit(f"Refusing to refresh through a symbolic link: {current}")
        current = current.parent
    if target.exists():
        if source.is_dir() and not target.is_dir():
            raise SystemExit(f"Runtime directory conflicts with an existing file: {target}")
        if source.is_file() and not target.is_file():
            raise SystemExit(f"Runtime file conflicts with an existing non-file: {target}")

for source in items:
    target = target_root / source.relative_to(source_root)
    if source.is_dir():
        created = not target.exists()
        target.mkdir(parents=True, exist_ok=True)
        if created and owner:
            os.chown(target, owner.pw_uid, owner.pw_gid)
        continue
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    if owner:
        os.chown(target, owner.pw_uid, owner.pw_gid)
PY
		[ -x "$INSTALL_DIR/opendock" ] || chmod 700 "$INSTALL_DIR/opendock"
		chmod 600 "$INSTALL_DIR/.opendock-install"
		log "OpenDock runtime files refreshed; local configuration and installed services were preserved"
	else
		if [ -d "$INSTALL_DIR" ]; then
			if [ -n "$(find "$INSTALL_DIR" -mindepth 1 -maxdepth 1 -print -quit)" ]; then
				die "${INSTALL_DIR} changed during installation and is no longer empty. No files were copied there."
			fi
			rmdir "$INSTALL_DIR" || die "Could not prepare the empty OpenDock root at ${INSTALL_DIR}. No files were copied there."
		elif [ -L "$INSTALL_DIR" ]; then
			die "${INSTALL_DIR} appeared as a symbolic link during installation. No files were copied there."
		fi
		mv "$install_stage" "$INSTALL_DIR"
		if [ "$(id -u)" -eq 0 ] && [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != root ]; then
			local owner_group
			owner_group="$(id -gn "$SUDO_USER")"
			chown -R "$SUDO_USER:$owner_group" "$INSTALL_DIR"
		fi
	fi
	if [ -n "$archive_file" ]; then
		rm -f "$archive_file"
	fi
	rm -rf "$extract_root"
	trap - EXIT
	if [ "$runtime_mode" = "refresh" ]; then
		log "OpenDock runtime refresh complete"
	else
		log "Installed the minimal OpenDock runtime without Git metadata, CI files, tests, or developer docs"
	fi
}

ensure_cloudflare_env_file() {
	CLOUDFLARE_ENV_FILE="$INSTALL_DIR/config/cloudflare.env"
	mkdir -p "$INSTALL_DIR/config"
	if [ -L "$CLOUDFLARE_ENV_FILE" ]; then
		die "Refusing to use a symlink as the Cloudflare configuration file: $CLOUDFLARE_ENV_FILE"
	fi
	if [ -e "$CLOUDFLARE_ENV_FILE" ] && [ ! -f "$CLOUDFLARE_ENV_FILE" ]; then
		die "Cloudflare configuration path is not a regular file: $CLOUDFLARE_ENV_FILE"
	fi
	if [ ! -e "$CLOUDFLARE_ENV_FILE" ]; then
		if [ -f "$INSTALL_DIR/config/cloudflare.env.default" ]; then
			(umask 077; cp "$INSTALL_DIR/config/cloudflare.env.default" "$CLOUDFLARE_ENV_FILE")
		else
			(umask 077; : > "$CLOUDFLARE_ENV_FILE")
		fi
	fi
	chmod 600 "$CLOUDFLARE_ENV_FILE"
	if [ "$(id -u)" -eq 0 ] && [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != root ]; then
		chown "$SUDO_USER:$(id -gn "$SUDO_USER")" "$CLOUDFLARE_ENV_FILE"
	fi
}

write_cloudflared_token() {
	local token="$1"
	CLOUDFLARED_TOKEN="$token" python3 - "$CLOUDFLARE_ENV_FILE" <<'PY'
import os, sys, tempfile
from pathlib import Path
path = Path(sys.argv[1])
lines = path.read_text().splitlines()
key = "CLOUDFLARED_TUNNEL_TOKEN"
line = f"{key}={os.environ['CLOUDFLARED_TOKEN']}"
for index, current in enumerate(lines):
    if current.strip().startswith(f"{key}="):
        lines[index] = line
        break
else:
    lines.append(line)
fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
try:
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write("\n".join(lines) + "\n")
    os.replace(temporary, path)
finally:
    if os.path.exists(temporary): os.unlink(temporary)
PY
	chmod 600 "$CLOUDFLARE_ENV_FILE"
	if [ "$(id -u)" -eq 0 ] && [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != root ]; then
		chown "$SUDO_USER:$(id -gn "$SUDO_USER")" "$CLOUDFLARE_ENV_FILE"
	fi
}

cloudflared_token_from_file() {
	python3 - "$CLOUDFLARE_ENV_FILE" <<'PY'
import sys
from pathlib import Path
for line in Path(sys.argv[1]).read_text().splitlines():
    if line.strip().startswith("CLOUDFLARED_TUNNEL_TOKEN="):
        value = line.split("=", 1)[1].strip()
        if len(value) > 1 and value[0] == value[-1] and value[0] in ("\"", "'"):
            value = value[1:-1]
        print(value, end="")
        break
PY
}

show_cloudflared_token_instructions() {
	cat <<EOF

Cloudflare Tunnel connector is not configured yet.
1. In Cloudflare Dashboard, open Networking > Tunnels and select your remotely-managed tunnel.
2. Choose Add a replica and copy the token from the displayed cloudflared command.
3. Add only the token (not the command) to this key in:
   $CLOUDFLARE_ENV_FILE
   CLOUDFLARED_TUNNEL_TOKEN=<paste-token-here>
   The file is private (mode 600) and excluded from Git and OpenDock sync.
4. Rerun bootstrap:
   bash "$INSTALL_DIR/scripts/bootstrap.sh"

The connector token is separate from the Cloudflare API token and Tunnel ID
used by './opendock setup cloudflare' for route and DNS synchronization.
EOF
}

read_cloudflared_token_if_requested() {
	local answer token
	if [ "$(wc -c < "$CLOUDFLARE_ENV_FILE")" -gt 1048576 ]; then
		die "Cloudflare configuration file is unexpectedly large. Check $CLOUDFLARE_ENV_FILE."
	fi
	token="$(cloudflared_token_from_file)"
	if [ -n "$token" ]; then
		write_cloudflared_token "$token"
		CLOUDFLARED_TOKEN="$token"
		return
	fi

	if [ ! -r /dev/tty ] || [ ! -w /dev/tty ]; then
		show_cloudflared_token_instructions
		return
	fi

	cat <<'EOF' >/dev/tty

Cloudflare Tunnel connector setup
Create or select a remotely-managed Tunnel in Cloudflare Dashboard:
  Networking > Tunnels > select tunnel > Add a replica
Copy the token from the cloudflared install command. OpenDock can store it
without echoing it, then install and start the connector service.
EOF
	printf 'Enter the Tunnel token now? [y/N] ' >/dev/tty
	IFS= read -r answer </dev/tty || answer=""
	case "$answer" in
		y|Y|yes|YES|Yes)
			printf 'Tunnel token (input hidden): ' >/dev/tty
			IFS= read -r -s token </dev/tty || token=""
			printf '\n' >/dev/tty
			if [ -z "$token" ]; then
				show_cloudflared_token_instructions
				return
			fi
			if [[ "$token" == *[[:space:]]* ]]; then
				unset token
				die "Tunnel token must be pasted without spaces or line breaks."
			fi
			write_cloudflared_token "$token"
			CLOUDFLARED_TOKEN="$token"
			unset token
			;;
		*)
			show_cloudflared_token_instructions
			return
			;;
	esac
}

cloudflared_supports_token_file() {
	local help_output
	help_output="$(cloudflared tunnel run --help 2>&1)" || return 1
	[[ "$help_output" == *"--token-file"* ]]
}

install_cloudflared_linux() {
	if ! need_command cloudflared || ! cloudflared_supports_token_file; then
		log "Installing Cloudflare cloudflared from its signed APT repository"
		run_sudo install -d -m 0755 /usr/share/keyrings
		curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg \
			| run_sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
		printf '%s\n' 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main' \
			| run_sudo tee /etc/apt/sources.list.d/cloudflared.list >/dev/null
		run_sudo apt-get update
		run_sudo apt-get install -y cloudflared
	fi
	cloudflared_supports_token_file \
		|| die "Installed cloudflared does not support --token-file. Upgrade it and rerun bootstrap."

	local service_file temporary quoted_config_file quoted_runner quoted_python quoted_binary
	service_file=/etc/systemd/system/opendock-cloudflared.service
	if [ -e "$service_file" ] && ! grep -q 'Description=OpenDock Cloudflare Tunnel connector' "$service_file"; then
		die "A different service already uses $service_file; refusing to replace it."
	fi
	if pgrep -f '[c]loudflared.*tunnel.*run' >/dev/null 2>&1 \
		&& ! run_sudo systemctl is-active --quiet opendock-cloudflared.service; then
		warn "A cloudflared connector is already running outside OpenDock's systemd service. Leaving it untouched; bootstrap will continue."
		warn "If it already connects this Tunnel, no additional connector is needed. To manage it with OpenDock, stop its current service and rerun bootstrap."
		return
	fi
	temporary="$(mktemp)"
	quoted_config_file="${CLOUDFLARE_ENV_FILE//\\/\\\\}"
	quoted_config_file="${quoted_config_file//\"/\\\"}"
	quoted_config_file="\"${quoted_config_file}\""
	quoted_runner="${INSTALL_DIR}/scripts/run-cloudflared.py"
	quoted_runner="${quoted_runner//\\/\\\\}"
	quoted_runner="${quoted_runner//\"/\\\"}"
	quoted_runner="\"${quoted_runner}\""
	quoted_python="$(command -v python3)"
	quoted_python="${quoted_python//\\/\\\\}"
	quoted_python="${quoted_python//\"/\\\"}"
	quoted_python="\"${quoted_python}\""
	quoted_binary="$(command -v cloudflared)"
	quoted_binary="${quoted_binary//\\/\\\\}"
	quoted_binary="${quoted_binary//\"/\\\"}"
	quoted_binary="\"${quoted_binary}\""
	cat > "$temporary" <<EOF
[Unit]
Description=OpenDock Cloudflare Tunnel connector
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
ExecStart=$quoted_python $quoted_runner --config $quoted_config_file --cloudflared $quoted_binary
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOF
	run_sudo install -o root -g root -m 0644 "$temporary" "$service_file"
	rm -f "$temporary"
	run_sudo systemctl daemon-reload
	run_sudo systemctl enable opendock-cloudflared.service >/dev/null
	if run_sudo systemctl is-active --quiet opendock-cloudflared.service; then
		run_sudo systemctl restart opendock-cloudflared.service
	else
		run_sudo systemctl start opendock-cloudflared.service
	fi
	run_sudo systemctl is-active --quiet opendock-cloudflared.service \
		|| die "cloudflared did not start. Inspect: sudo journalctl -u opendock-cloudflared -n 50 --no-pager"
	log "Cloudflare Tunnel connector is enabled and running as a systemd service"
}

install_cloudflared_macos() {
	if ! need_command brew; then
		warn "Homebrew is required to install cloudflared on macOS. The token is saved in $CLOUDFLARE_ENV_FILE. Install Homebrew, then rerun bootstrap."
		return
	fi
	if ! need_command cloudflared || ! cloudflared_supports_token_file; then
		brew install cloudflared
	fi
	cloudflared_supports_token_file \
		|| die "Installed cloudflared does not support --token-file. Upgrade it and rerun bootstrap."

	local launch_agents log_dir plist_file launch_domain cloudflared_binary python_binary runner_file
	launch_agents="$HOME/Library/LaunchAgents"
	log_dir="$HOME/Library/Logs/OpenDock"
	plist_file="$launch_agents/com.opendock.cloudflared.plist"
	launch_domain="gui/$(id -u)"
	cloudflared_binary="$(command -v cloudflared)"
	python_binary="$(command -v python3)"
	runner_file="${INSTALL_DIR}/scripts/run-cloudflared.py"
	if pgrep -f '[c]loudflared.*tunnel.*run' >/dev/null 2>&1 \
		&& ! launchctl print "$launch_domain/com.opendock.cloudflared" >/dev/null 2>&1; then
		warn "A cloudflared connector is already running outside OpenDock's LaunchAgent. Leaving it untouched; bootstrap will continue."
		warn "If it already connects this Tunnel, no additional connector is needed. To manage it with OpenDock, stop its current service and rerun bootstrap."
		return
	fi
	mkdir -p "$launch_agents" "$log_dir"
	CLOUDFLARED_BINARY="$cloudflared_binary" \
	CLOUDFLARED_PYTHON="$python_binary" \
	CLOUDFLARED_RUNNER="$runner_file" \
	CLOUDFLARE_ENV_FILE="$CLOUDFLARE_ENV_FILE" \
	CLOUDFLARED_PLIST="$plist_file" \
	CLOUDFLARED_LOG_DIR="$log_dir" \
	python3 - <<'PY'
import os
import plistlib

entry = {
    "Label": "com.opendock.cloudflared",
    "ProgramArguments": [
		os.environ["CLOUDFLARED_PYTHON"], os.environ["CLOUDFLARED_RUNNER"],
		"--config", os.environ["CLOUDFLARE_ENV_FILE"],
		"--cloudflared", os.environ["CLOUDFLARED_BINARY"],
    ],
    "RunAtLoad": True,
    "KeepAlive": True,
    "StandardOutPath": os.path.join(os.environ["CLOUDFLARED_LOG_DIR"], "cloudflared.out.log"),
    "StandardErrorPath": os.path.join(os.environ["CLOUDFLARED_LOG_DIR"], "cloudflared.err.log"),
}
with open(os.environ["CLOUDFLARED_PLIST"], "wb") as stream:
    plistlib.dump(entry, stream)
PY
	chmod 600 "$plist_file"
	launchctl bootout "$launch_domain" "$plist_file" >/dev/null 2>&1 || true
	launchctl bootstrap "$launch_domain" "$plist_file"
	launchctl kickstart -k "$launch_domain/com.opendock.cloudflared"
	launchctl print "$launch_domain/com.opendock.cloudflared" >/dev/null \
		|| die "cloudflared launch agent did not start. Inspect $log_dir/cloudflared.err.log"
	log "Cloudflare Tunnel connector is running as a macOS LaunchAgent"
}

configure_cloudflared() {
	if [ "$CLOUDFLARED_SETUP" -ne 1 ]; then
		log "Skipping Cloudflare Tunnel connector setup by request"
		return
	fi
	if [ "$INSTALL_OPENDOCK" -ne 1 ]; then
		cat <<EOF

Cloudflared setup was deferred because OpenDock was not installed.
Rerun bootstrap with --install after choosing the OpenDock root.
EOF
		return
	fi
	ensure_cloudflare_env_file
	read_cloudflared_token_if_requested
	if [ -z "${CLOUDFLARED_TOKEN:-}" ]; then
		return
	fi
	case "$HOST_PLATFORM" in
		linux) install_cloudflared_linux ;;
		macos) install_cloudflared_macos ;;
	esac
	unset CLOUDFLARED_TOKEN
}

print_next_steps() {
	printf '\nOpenDock bootstrap is complete.\n'
	if [ "$DOCKER_GROUP_ADDED" -eq 1 ]; then
		printf '\nImportant:\n  %s was added to the docker group. Log out and log back in before using Docker without sudo.\n' "$target_user"
	fi
	if [ "$INSTALL_OPENDOCK" -eq 1 ]; then
		printf '\nNext steps:\n  cd "%s"\n' "$INSTALL_DIR"
		cat <<'EOF'
  ./opendock setup
  # Configure the primary domain and create private local configuration.
  ./opendock setup cloudflare
  # Configure Cloudflare API access for route/DNS sync.

  ./opendock check-config
  ./opendock search <service>
  ./opendock install <service>
  ./opendock launch <service>
EOF
	else
		printf '\nNext steps:\n  Rerun bootstrap with --install to create the OpenDock runtime.\n'
	fi
}

detect_platform
prepare_host
install_platform_runtime
configure_cloudflared
print_next_steps
