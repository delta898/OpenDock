# Adding a Service to OpenDock

> **Do not use this guide to add a new service.** It documents the legacy
> in-repository service implementation and its old `services/bundles/` layout.
> New service source belongs in OpenDock-Services and must follow the package
> and capability contracts in [`product-distribution.md`](product-distribution.md),
> [`catalog-and-package-contract.md`](catalog-and-package-contract.md), and
> [`service-contract.md`](service-contract.md). The Uptime Kuma Linux launch
> smoke check reached the public first-run database page; its database wizard,
> application readiness, and multi-domain lifecycle remain unverified.

The examples below describe how the current legacy Docker Compose catalog was
implemented. Static routes are configured separately with `./opendock route add
<hostname> static`; they do not use a service descriptor. A non-Docker runtime
needs a new platform contract and is outside this guide.

## What is discovered automatically?

The legacy service catalog scans `services/bundles/*/compose.yml`. Do not add
new products there: the agreed product model has no bundle category and all
services are installed from OpenDock-Services packages.
Each discovered Compose directory must also contain a valid `opendock.toml`.
With those files in place,
OpenDock discovers the service for `list`, target resolution, Compose lifecycle
commands, setup metadata, and descriptor-driven removal. The central `opendock`
dispatcher does not need a service-specific branch for behavior already covered
by the current contracts.

This is not always a service-directory-only change. A service exposed through
Caddy needs a matching snippet under `gateway/caddy/conf.d/`; the descriptor
names that snippet. Adding a new purpose-based group requires editing
`services/groups.conf`. A new shared dependency, config type, or capability
that the current platform contract does not support may require a platform or
core change first. Do not disguise a missing contract as service-specific
metadata.

## Contribution layout

공개 Docker 서비스를 추가할 때 작업은 보통 아래 두 위치에 함께 들어갑니다.

| 위치 | 파일 | 역할 |
| --- | --- | --- |
| `services/bundles/<service-id>/` | `compose.yml` | 앱 컨테이너, Compose 서비스 이름, 내부 포트, 볼륨 정의 |
| `services/bundles/<service-id>/` | `opendock.toml` | 서비스 등록, 설정 키, 기본 hostname, Caddy handler 이름, 제거 소유권 선언 |
| `services/bundles/<service-id>/` | `.env.default` | 기본값과 Renovate가 추적할 image tag |
| `services/bundles/<service-id>/` | `README.md` | 첫 실행, 데이터 위치, 업데이트와 제거 안내 |
| `services/bundles/<service-id>/routing/` | `<service-id>.caddy` | Caddy reverse proxy와 서비스별 HTTP 동작 |

세 위치 사이의 연결은 다음과 같습니다.

1. `opendock.toml`의 `[routing]`이 `handler_file`과 Caddy snippet 이름을 가리킵니다.
2. `<service-id>.caddy`는 같은 이름의 snippet을 정의하고,
   `reverse_proxy <compose-service>:<internal-port>`를 사용합니다.
3. `<compose-service>`는 `compose.yml`의 서비스 이름과 같아야 하며, 앱은
   Caddy가 연결된 `shared-net`에 참여해야 합니다.
4. `[routing].subdomain_key`는 `[[setup.fields]]`에 선언한 키여야 하고,
   그 키는 `.env.default`에도 안전한 기본값으로 선언합니다.

예를 들어 `example-app`의 연결은 다음처럼 맞춥니다.

```text
services/bundles/example-app/compose.yml
  Compose service: example-app
  Internal port: 8080
  Shared network: shared-net

services/bundles/example-app/opendock.toml
  routing.handler_file = "routing/example-app.caddy"
  routing.caddy_handler = "example_app_proxy"
  routing.subdomain_key = "EXAMPLE_APP_SUBDOMAIN"

services/bundles/example-app/.env.default
  EXAMPLE_APP_SUBDOMAIN=example

services/bundles/example-app/routing/example-app.caddy
  (example_app_proxy) { reverse_proxy example-app:8080 ... }
```

이 중 하나의 이름이나 포트가 다르면 catalog 발견은 성공하더라도 route 검증이나
실제 연결이 실패할 수 있습니다. 서비스 추가 시 두 위치의 파일을 함께 검토하세요.

```text
services/bundles/<service-id>/
  compose.yml             required; Docker Compose application
  opendock.toml           required; registration, setup, routing, removal
  .env.default            tracked non-secret defaults and image versions
  README.md               recommended; usage, storage, updates, security
  opendock.py             optional; declared capability handlers
  commands/               optional; executable service-specific commands
  data/                   runtime data only when bind mounts are required

services/bundles/<service-id>/routing/<service-id>.caddy  required when public Docker routing is enabled
```

Use a stable lowercase ID with hyphens, matching the directory and descriptor
`service_id`. Convert hyphens to underscores and uppercase for the environment
variable prefix: `photo-stack` becomes `PHOTO_STACK_`.

## Declare the service

Start from the smallest similar bundled service, such as
`services/bundles/uptime-kuma/`. A minimal public service descriptor looks like this:

```toml
schema_version = 1
service_id = "example-app"
display_name = "Example App"
dependencies = ["infra"]
capabilities = []

[[setup.fields]]
name = "EXAMPLE_APP_SUBDOMAIN"
kind = "defaulted-choice"
default = "example"

[routing]
subdomain_key = "EXAMPLE_APP_SUBDOMAIN"
caddy_handler = "example_app_proxy"

[removal]
# Compose named volumes are removed by Compose. List only service-owned host paths.
data_paths = []
```

For large user-owned files, add a defaulted service path field, declare the
container mount, and keep the default inside a declared removal data path. In
the minimal descriptor above, change `data_paths = []` to `data_paths = ["media"]`:

```toml
[[setup.fields]]
name = "EXAMPLE_APP_MEDIA_PATH"
kind = "defaulted-choice"
default = "./media"
note = "Use an existing absolute host directory to override the default."

[[storage.mounts]]
name = "media"
setting_key = "EXAMPLE_APP_MEDIA_PATH"
container_path = "/media"
access = "read-only"
```

Add `EXAMPLE_APP_MEDIA_PATH=./media` to `.env.default`, and use a long Compose
bind mount with `bind.create_host_path: false`. `access` is `read-only` or
`read-write`; choose what the application needs. Keep database paths separate.
The user can keep the default or set an absolute host path through
`./opendock setup <service>`. OpenDock creates a missing checkout-local default
directory during launch/up, but a custom path must already exist. It checks
path existence and access, not the filesystem or disk type. `purge` shows and
removes the configured data directory after confirmation. Use the same
service-specific path contract for WordPress' complete webroot; do not assume
it can safely expose only uploads without changing its current mount layout.

Opt in only for user-owned data that benefits from a selectable host location;
do not add settings for every named volume or bind mount. For example,
WordPress can expose its complete `/var/www/html` webroot, while Hermes' app
state includes credentials and its sandbox path is coupled to a nested Docker
mount and sandbox-container cleanup. That needs a separate design review before
making the sandbox path user-configurable.

The top-level `dependencies` list names platform components such as `infra` or
`gateway`. `[setup].dependencies` means something different: it names an
existing shared setup group such as `mariadb` or `postgres`. For example:

```toml
[setup]
dependencies = ["postgres"]
optional_config = ["mail"]
```

Only declare groups and optional config sections that already exist. Each setup
key must use the service prefix and an accepted field kind:

- `required-user`: a value the user must supply;
- `defaulted-choice`: a user-editable value with a safe default;
- `initial-credential`: an initial app credential with user-facing handling;
- `secret-user`: a user-supplied secret, stored privately and masked;
- `generated-secret`: a generated value using `url-safe`, `alphanumeric`, or
  `hex`, or a service-declared generation capability.

Keep secrets out of `.env.default`, Compose files, examples, and logs. Put
ordinary defaults and Renovate-tracked image versions in `.env.default`. To
track an image version with Renovate, add the supported annotation immediately
above the variable:

```dotenv
# renovate: datasource=docker depName=vendor/example-app
EXAMPLE_APP_VERSION=1.2.3
```

Compose should interpolate that value, for example:

```yaml
services:
  example-app:
    image: vendor/example-app:${EXAMPLE_APP_VERSION}
```

## Routing and Caddy

The `[routing]` section opts the service into a default hostname derived from
`STACK_DOMAIN` and the declared subdomain field. Its `handler_file` must name a
package-owned Caddy file and `caddy_handler` must match its snippet name. A typical
snippet is:

```caddyfile
(example_app_proxy) {
    import common_proxy
    import security_headers

    reverse_proxy example-app:8080 {
        import forwarded_https
    }
}
```

Use the actual Compose service name and internal port. Add service-specific
WebSocket, path, header, or timeout behavior only when the upstream requires it.
Without routing metadata, the service can still be managed as a Compose target,
but OpenDock will not create a default public route for it.

## Declare removal ownership

Every new service must declare its removal boundary before it is considered
complete. OpenDock removes the Compose project and named volumes, then handles
declared routes, shared database objects, host data paths, private config files,
and extra images according to the descriptor. The user receives a plan and
must confirm `REMOVE <service-id>`.

Audit each mount and resource:

- Compose named volumes are covered by Compose removal; do not repeat them as
  host paths.
- Add bind-mounted user data under `data_paths` only if complete removal should
  delete it. Explain the deletion in the service README.
- Put private, non-Compose config files under `config_files`; the remover makes
  a permission-restricted backup before deletion.
- Add `preserve_paths` for tracked placeholders or content that must survive
  beneath a removable data path.
- Declare `extra_images` and `orphan_containers` only when ownership can be
  verified. Orphan containers must mount a declared data path and be selected
  by a unique label.
- If the service owns a database/schema in shared MariaDB or PostgreSQL, declare
  `removal.shared_database` with its service-prefixed database and role keys.
  Do not remove shared containers or shared volumes.

Never claim a path just because it is mounted. Determine whether it contains
application state, user data, tracked configuration, or shared state, then
document what removal does to it.

## Add service-specific behavior only when needed

Most services need only Compose plus descriptor metadata. Do not add an empty
`opendock.py` or a no-op hook. If the service needs application-aware behavior,
declare only capabilities supported by API v1 and implement each declared
handler in `services/bundles/<service-id>/opendock.py`:

```python
OPENDOCK_CAPABILITY_API_VERSION = 1
```

Current capability names are `runtime_environment`, `prepare`,
`plan_secrets`, `generate_secrets`, `validate_config`, and `post_launch`. Read
the contract and result types in `scripts/opendock_capabilities.py` and the
examples in Hermes, Mastodon, and Supabase before implementing one. Handlers
must be idempotent where applicable, use only the scoped context passed to
them, return the declared typed result, and avoid calling the top-level CLI
recursively. The local Python handler is trusted repository code, not a
sandbox.

Service commands are also optional. Put executable commands in
`services/bundles/<service-id>/commands/<name>` and declare matching `[[commands]]`
metadata. The catalog requires every declared command to have an executable
file. Keep these operations service-specific; do not add a top-level CLI
command for one application.

## Review and verification checklist

From the repository root:

```sh
./opendock list services
./opendock service <service-id>
./opendock check-config <service-id>
python3 -m unittest discover -s tests
```

The first two commands exercise catalog discovery and service command metadata.
`check-config` validates the service after required settings have been
configured. Run the test suite with the repository's supported Python version
(3.11 or newer). Also review the Compose rendering and Caddy configuration in
an isolated development environment before publishing the service.

For a service with routing, check that `route show` recognizes its default
hostname, then add a separate test hostname and inspect the route before
launching. A real `launch` can start containers and publish Cloudflare routes;
do this only in an environment where those effects are intended. Exercise
`purge <service-id> --dry-run` before any confirmed purge. Full purge
verification belongs on a clean isolated host, including checks that shared
infrastructure and unrelated services survive.

Before requesting review, verify that:

- the service appears without editing a central service registry or CLI branch;
- every setup key is owned by the service and secrets are private;
- image version and Renovate metadata agree with the official image;
- all mounts, networks, internal ports, health behavior, and architectures match
  the upstream documentation;
- the route handler exists and points at the correct Compose service and port;
- the removal plan preserves shared and tracked data;
- the README explains first launch, user data, updates, and removal.

Follow [Command and Service Ownership](command-architecture.md) for the common
versus service-owned boundary. Use the [AI service contribution prompt](prompts/add-service.md)
as a starting point when asking an AI assistant to prepare the contribution.
