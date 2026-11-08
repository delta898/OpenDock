#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
OPEN_DOCK_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
SERVICES_ROOT="${OPENDOCK_SERVICES_ROOT:-${OPEN_DOCK_ROOT}/../OpenDock-Services}"

usage() {
	cat <<'EOF'
Usage: ./scripts/test-service.sh <service-id> [--allow-host-docker-socket]

Build a local package from OpenDock-Services, install it in a disposable
OpenDock checkout, verify its HTTP route through isolated Caddy, and clean up.

The Docker socket option grants the test service control over the selected host
Docker daemon. Use it only on a disposable Docker host.
Set OPENDOCK_SERVICES_ROOT if OpenDock-Services is not next to this checkout.
EOF
}

if [[ $# -lt 1 || $# -gt 2 || "$1" == "-h" || "$1" == "--help" ]]; then
	usage
	[[ $# -eq 1 && ( "$1" == "-h" || "$1" == "--help" ) ]] && exit 0
	exit 2
fi

SERVICE_ID="$1"
ALLOW_HOST_DOCKER_SOCKET=0
if [[ $# -eq 2 ]]; then
	if [[ "$2" != "--allow-host-docker-socket" ]]; then
		printf 'Unknown option: %s\n' "$2" >&2
		exit 2
	fi
	ALLOW_HOST_DOCKER_SOCKET=1
fi
if [[ ! "$SERVICE_ID" =~ ^[a-z][a-z0-9-]*$ ]]; then
	printf 'Invalid service ID: %s\n' "$SERVICE_ID" >&2
	exit 2
fi

SERVICES_ROOT="$(cd -- "$SERVICES_ROOT" 2>/dev/null && pwd)" || {
	printf 'OpenDock-Services checkout not found. Set OPENDOCK_SERVICES_ROOT.\n' >&2
	exit 2
}
PACKAGE_SCRIPT="${SERVICES_ROOT}/scripts/package-service.py"
EXPERIMENT_SOURCE="${SERVICES_ROOT}/services/experiments/${SERVICE_ID}"
EXTENSION_SOURCE="${SERVICES_ROOT}/services/extensions/${SERVICE_ID}"
if [[ -d "$EXPERIMENT_SOURCE" && -d "$EXTENSION_SOURCE" ]]; then
	printf 'Both experiment and extension sources exist for %s; resolve the duplicate first.\n' "$SERVICE_ID" >&2
	exit 2
elif [[ -d "$EXPERIMENT_SOURCE" ]]; then
	SERVICE_SOURCE="$EXPERIMENT_SOURCE"
elif [[ -d "$EXTENSION_SOURCE" ]]; then
	SERVICE_SOURCE="$EXTENSION_SOURCE"
else
	printf 'No service source found for %s under services/experiments or services/extensions.\n' "$SERVICE_ID" >&2
	exit 2
fi
if [[ ! -f "$PACKAGE_SCRIPT" ]]; then
	printf 'Missing package builder: %s\n' "$PACKAGE_SCRIPT" >&2
	exit 2
fi
if [[ ! -f "${OPEN_DOCK_ROOT}/scripts/opendock_local_test.py" ]]; then
	printf 'OpenDock local-test support is missing from this checkout.\n' >&2
	exit 2
fi
if ! command -v docker >/dev/null 2>&1 || ! command -v curl >/dev/null 2>&1; then
	printf 'Both Docker and curl are required.\n' >&2
	exit 2
fi

LOCAL_VERSION="$(python3 - "$SERVICE_SOURCE/opendock.toml" "$SERVICE_ID" <<'PY'
import re
import sys
import time
import tomllib

with open(sys.argv[1], "rb") as source:
    descriptor = tomllib.load(source)
service_id = descriptor.get("service_id")
version = descriptor.get("version", "0.1.0")
if service_id != sys.argv[2]:
    raise SystemExit("Requested service ID does not match opendock.toml.")
match = re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z.-]+)?", version)
if not match:
    raise SystemExit("Service descriptor needs a valid SemVer package version seed.")
base = ".".join(match.group(index) for index in (1, 2, 3))
print(f"{base}-local.{time.time_ns()}")
PY
)"

TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/opendock-service-test.XXXXXX")"
PACKAGE_PATH="${TEMP_DIR}/${SERVICE_ID}.zip"
START_LOG="${TEMP_DIR}/start.log"
RUNTIME_ROOT=""

cleanup() {
	local status=$?
	trap - EXIT
	if [[ -n "$RUNTIME_ROOT" && -f "${RUNTIME_ROOT}/config/local-test/session.json" ]]; then
		printf '\n==> %s: remove disposable test environment\n' "$SERVICE_ID"
		if ! "${OPEN_DOCK_ROOT}/opendock" local-test clean "$RUNTIME_ROOT"; then
			printf 'Cleanup failed; disposable runtime preserved at %s\n' "$RUNTIME_ROOT" >&2
			status=1
		fi
	fi
	rm -rf -- "$TEMP_DIR"
	if [[ $status -eq 0 ]]; then
		printf '\nRESULT: PASS — %s package, isolated launch, Caddy route, cleanup\n' "$SERVICE_ID"
	else
		printf '\nRESULT: FAIL — %s (exit %s)\n' "$SERVICE_ID" "$status" >&2
	fi
	exit "$status"
}
trap cleanup EXIT

printf '==> %s: build local package %s\n' "$SERVICE_ID" "$LOCAL_VERSION"
python3 "$PACKAGE_SCRIPT" "$SERVICE_SOURCE" "$LOCAL_VERSION" "$PACKAGE_PATH"

printf '\n==> %s: start isolated OpenDock + Caddy test\n' "$SERVICE_ID"
set +e
if [[ $ALLOW_HOST_DOCKER_SOCKET -eq 1 ]]; then
	"${OPEN_DOCK_ROOT}/opendock" local-test start "$PACKAGE_PATH" \
		--domain "${SERVICE_ID}.local.test" --allow-host-docker-socket 2>&1 | tee "$START_LOG"
else
	"${OPEN_DOCK_ROOT}/opendock" local-test start "$PACKAGE_PATH" \
		--domain "${SERVICE_ID}.local.test" 2>&1 | tee "$START_LOG"
fi
start_status=${PIPESTATUS[0]}
set -e
if [[ $start_status -ne 0 ]]; then
	RUNTIME_ROOT="$(sed -n 's/^Preserved test root for recovery: //p' "$START_LOG" | tail -n 1)"
	exit "$start_status"
fi

RUNTIME_ROOT="$(sed -n 's/^Runtime root: //p' "$START_LOG" | tail -n 1)"
if [[ -z "$RUNTIME_ROOT" || ! -f "${RUNTIME_ROOT}/config/local-test/session.json" ]]; then
	printf 'local-test did not report a valid disposable runtime path.\n' >&2
	exit 1
fi
HTTP_PORT="$(python3 - "${RUNTIME_ROOT}/config/local-test/session.json" <<'PY'
import json
import sys
with open(sys.argv[1]) as source:
    print(json.load(source)["http_port"])
PY
)"
URL="http://${SERVICE_ID}.local.test:${HTTP_PORT}/"

printf '\n==> %s: check Caddy route %s\n' "$SERVICE_ID" "$URL"
response=""
for attempt in $(seq 1 30); do
	if response="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
		--max-time 5 --resolve "${SERVICE_ID}.local.test:${HTTP_PORT}:127.0.0.1" \
		"$URL" 2>"${TEMP_DIR}/curl.err")"; then
		if [[ "$response" =~ ^[1-4][0-9][0-9]$ ]]; then
			break
		fi
	fi
	response=""
	sleep 2
done
if [[ -z "$response" ]]; then
	printf 'No HTTP response from the service through Caddy after 60 seconds.\n' >&2
	if [[ -s "${TEMP_DIR}/curl.err" ]]; then
		tail -n 3 "${TEMP_DIR}/curl.err" >&2
	fi
	exit 1
fi
printf 'Caddy returned HTTP %s for %s.\n' "$response" "$URL"

exit 0
