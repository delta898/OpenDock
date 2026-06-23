#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/delta898/OpenDock.git"
INSTALL_DIR="${HOME}/OpenDock"
INSTALL_DIR_SET=0
BRANCH="main"
CLONE_REPO=1
FORCE=0
DOCKER_GROUP_ADDED=0

usage() {
	cat <<'USAGE'
Usage:
  bootstrap-ubuntu.sh [options]

Options:
  --clone              Clone the OpenDock repository after installing packages. This is the default.
  --no-clone           Do not clone the repository.
  --dir <path>         Clone destination. Default: $HOME/OpenDock
  --repo <url>         Git repository URL. Default: https://github.com/delta898/OpenDock.git
  --branch <name>      Git branch to clone. Default: main
  --force              Continue even when the OS check is not an Ubuntu 24.04+ host.
  -h, --help           Show this help.

Examples:
  curl -fsSL https://raw.githubusercontent.com/delta898/OpenDock/main/scripts/bootstrap-ubuntu.sh | bash
  curl -fsSL https://raw.githubusercontent.com/delta898/OpenDock/main/scripts/bootstrap-ubuntu.sh | bash -s -- --no-clone
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

while [ "$#" -gt 0 ]; do
	case "$1" in
		--clone)
			CLONE_REPO=1
			shift
			;;
		--no-clone)
			CLONE_REPO=0
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
			shift 2
			;;
		--branch)
			[ "$#" -ge 2 ] || die "--branch requires a branch name"
			BRANCH="$2"
			shift 2
			;;
		--force)
			FORCE=1
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

need_command() {
	command -v "$1" >/dev/null 2>&1
}

prepare_privileges() {
	need_command apt-get || die "apt-get was not found. This script targets Ubuntu."

	if [ "$(id -u)" -ne 0 ] && ! need_command sudo; then
		die "sudo is required when running as a non-root user."
	fi

	if [ "$(id -u)" -eq 0 ] && [ -n "${SUDO_USER:-}" ] && [ "$INSTALL_DIR_SET" -eq 0 ]; then
		user_home="$(getent passwd "$SUDO_USER" | cut -d: -f6)"
		if [ -n "$user_home" ]; then
			INSTALL_DIR="${user_home}/OpenDock"
		fi
	fi
}

run_sudo() {
	if [ "$(id -u)" -eq 0 ]; then
		"$@"
	else
		sudo "$@"
	fi
}

version_ge_24() {
	major="${1%%.*}"
	[ "$major" -ge 24 ] 2>/dev/null
}

check_os() {
	if [ ! -r /etc/os-release ]; then
		[ "$FORCE" -eq 1 ] && return
		die "Could not read /etc/os-release. Use --force to continue anyway."
	fi

	# shellcheck disable=SC1091
	. /etc/os-release

	if [ "${ID:-}" != "ubuntu" ]; then
		[ "$FORCE" -eq 1 ] && {
			warn "Expected Ubuntu, found ${PRETTY_NAME:-unknown OS}. Continuing because --force was set."
			return
		}
		die "This bootstrap script targets Ubuntu Server 24.04 or newer. Found ${PRETTY_NAME:-unknown OS}."
	fi

	if ! version_ge_24 "${VERSION_ID:-0}"; then
		[ "$FORCE" -eq 1 ] && {
			warn "Expected Ubuntu 24.04 or newer, found ${VERSION_ID:-unknown}. Continuing because --force was set."
			return
		}
		die "This bootstrap script targets Ubuntu Server 24.04 or newer. Found ${VERSION_ID:-unknown}."
	fi

	log "Detected ${PRETTY_NAME}"
}

install_packages() {
	log "Updating apt package lists"
	run_sudo apt-get update

	log "Installing base prerequisites"
	run_sudo apt-get install -y git make curl ca-certificates

	if need_command docker && docker compose version >/dev/null 2>&1; then
		log "Docker and Docker Compose are already installed"
	else
		log "Installing Docker from Ubuntu repositories"
		run_sudo apt-get install -y docker.io docker-compose-v2
	fi
}

enable_docker() {
	if need_command systemctl; then
		log "Enabling Docker service"
		run_sudo systemctl enable --now docker
	else
		warn "systemctl was not found. Skipping Docker service enable/start."
	fi
}

configure_docker_group() {
	target_user="${SUDO_USER:-${USER:-}}"

	if [ -z "$target_user" ]; then
		warn "Could not detect the login user. Skipping docker group setup."
		return
	fi

	if [ "$target_user" = "root" ]; then
		warn "Running as root. Skipping docker group setup."
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

verify_docker() {
	log "Checking Docker"
	run_sudo docker --version
	run_sudo docker compose version
}

clone_repository() {
	if [ "$CLONE_REPO" -ne 1 ]; then
		return
	fi

	log "Cloning OpenDock"

	if [ -e "$INSTALL_DIR" ]; then
		if [ -d "$INSTALL_DIR/.git" ]; then
			warn "${INSTALL_DIR} already exists and looks like a Git repository. Skipping clone."
			return
		fi
		die "${INSTALL_DIR} already exists. Choose another path with --dir."
	fi

	git clone --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
}

print_next_steps() {
	cat <<EOF

OpenDock bootstrap is complete.
EOF

	if [ "$DOCKER_GROUP_ADDED" -eq 1 ]; then
		cat <<EOF

Important:
  ${target_user} was added to the docker group. Log out and log back in
  before running Docker without sudo.
EOF
	fi

	cat <<EOF

Next steps:
EOF

	if [ "$CLONE_REPO" -eq 1 ]; then
		cat <<EOF
  cd "$INSTALL_DIR"
EOF
	else
		cat <<EOF
  git clone "$REPO_URL" "$INSTALL_DIR"
  cd "$INSTALL_DIR"
EOF
	fi

	cat <<'EOF'
  cp common.env.example common.env
  nano common.env

  # Optional Cloudflare API sync:
  cp cloudflare.env.example cloudflare.env
  nano cloudflare.env

  make check-config
  make launch

Optional:
  Run sudo apt upgrade later if you want to update the whole OS.
EOF
}

prepare_privileges
check_os
install_packages
enable_docker
configure_docker_group
verify_docker
clone_repository
print_next_steps
