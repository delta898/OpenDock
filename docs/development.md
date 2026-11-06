# Development Notes

> These notes describe the current implementation. The greenfield product
> target is in [`product-distribution.md`](product-distribution.md) and its
> linked contracts. Treat existing paths and commands below as references, not
> backward-compatibility requirements.

> **Current product rule:** there is no bundle category. New service source is
> developed in OpenDock-Services, published to the static catalog, and installed
> under `services/extensions/<service-id>/releases/<version>`. The older
> `services/bundles/` paths below describe migration residue in this checkout;
> do not use them for new services. Package `update`, `search`, and `install`
> have been exercised with the dev catalog. A Linux Uptime Kuma launch reached
> its public first-run database page; choosing and configuring the database is
> user-owned. Wizard completion, application readiness, purge, and
> multi-domain instances remain unverified.

This document describes the conventions used by OpenDock. It is intended for maintainers and advanced users who want to add or modify services.

## Design Goals

- Services should be easy to start from the repository root.
- Adding a service should not require editing the CLI dispatcher.
- `STACK_DOMAIN` should produce predictable default hostnames; `domains.conf` can map any hostname to a service or static directory.
- Public routes should be discoverable from repository structure.
- Cloudflare Tunnel is the default public exposure layer.
- Beginner-facing setup should stay small: `./opendock setup`, then
  `./opendock launch <hostname>`; Cloudflare configuration is required before
  public launch.

## Ubuntu Bootstrap

`scripts/bootstrap-ubuntu.sh` prepares a fresh Ubuntu Server host for OpenDock.

Supported target:

```text
Ubuntu Server 24.04 or newer
```

The script intentionally uses Ubuntu packages instead of adding Docker's official apt repository. This keeps the beginner path shorter and avoids extra keyring/source-list steps. If Docker and Docker Compose are already installed, it does not replace them.

Base packages:

```text
git
python3
curl
ca-certificates
```

Docker packages installed only when Docker or Docker Compose is missing:

```text
docker.io
docker-compose-v2
```

The script also:

- runs `apt-get update`
- enables and starts Docker with systemd when available
- adds the login user to the `docker` group
- verifies `docker --version`
- verifies `docker compose version`
- clones the repository to `~/OpenDock` by default
- supports `--no-clone` for prerequisite-only setup
- prints next steps

The script intentionally does not:

- run `apt upgrade`
- initialize or edit the owner-specific files under `config/`
- create or edit `config/cloudflare.env` (use `./opendock setup cloudflare`)
- create a Cloudflare Tunnel
- run `./opendock launch`

This keeps system preparation separate from stack configuration and avoids hiding important security choices from the user.

## Directory Conventions

Core projects live at the repository root:

```text
infra/      shared infrastructure
gateway/    Caddy reverse proxy
```

Bundled service definitions live under:

```text
services/bundles/<service-id>/compose.yml
```

Optional package source lives in the sibling OpenDock-Services repository at
`services/extensions/<service-id>/`. Installed package releases are registered
under OpenDock's `services/extensions/` directory after installation. Previous
service directories are kept only in a local, gitignored `archive/` folder;
the catalog and sync workflow ignore that archive.

Examples:

```text
OpenDock-Services/services/extensions/wordpress/compose.yml
OpenDock-Services/services/extensions/n8n/compose.yml
```

## CLI Target Discovery

The common CLI and service-owned behavior boundary is documented in
[Command and Service Ownership](command-architecture.md). When adding a command
capability, use that contract to decide whether it belongs in the common
workflow or under `OpenDock-Services/services/extensions/<name>/`; do not add
service-specific branches to the central dispatcher.

The active service catalog discovers only installed package releases listed in:

```text
services/extensions/installed.toml
```

Legacy bundle directories and `services/groups.conf` entries that reference
uninstalled services are not active. New service source belongs in
OpenDock-Services and becomes visible after package installation registers its
release.

This is why new services do not need CLI dispatcher changes.

Shared platform components such as `infra/` and `gateway/` have a separate
catalog and descriptor. `infra/opendock.toml` owns the shared setting keys,
setup fields, secret generator declarations, and dependency groups such as
`mariadb` and `postgres`; `gateway/opendock.toml` owns gateway setting keys. A
service declares only the shared groups it needs in its installed package
descriptor; the common setup and secret coordinators resolve those declarations.
Platform config ownership is also derived from the
component descriptors. Shared concerns keep their configuration descriptor
and tracked defaults together under `config/shared/`: `mail.toml` with
`mail.env.default`, and `database.toml` with `database.env.default`. The TOML
descriptor declares keys, shared dependency groups, and optional setup prompts;
the defaults file contains values only.

SMTP is an optional shared config section. Services that use it declare
`setup.optional_config = ["mail"]`; common setup offers the relay once, and
starting a service offers it after required config validation if the user has
not configured or previously skipped it. `MARIADB_CLIENT_VERSION` is declared
by the shared database config and is accepted from a legacy service config only
when that service declares the matching `mariadb` setup dependency. Infra still
owns the MariaDB service, shared dependency group, and database removal adapter.

## Contributing a service

The contributor workflow is documented in [Adding a Service to OpenDock](adding-services.md).
For an AI-assisted contribution, start from the [service contribution meta prompt](prompts/add-service.md).

OpenDock treats a service as a small extension unit. The OpenDock-Services
contribution layout is:

```text
OpenDock-Services/services/extensions/<stable-service-id>/
  opendock.toml          descriptor and capability/API versions
  compose.yml            runtime definition
  .env.default           tracked defaults and image versions
  commands/              optional user-invoked service commands
  opendock.py            optional typed capability handlers
```

Optional service packages use the same contribution shape under
`OpenDock-Services/services/extensions/<stable-service-id>/` and add a
`routing/` directory when they need service-specific Caddy handlers.

The descriptor is the service's registration record. The catalog discovers it
alongside the Compose project; contributors should not add service-specific
branches to `opendock` or maintain another central name list. Keep IDs stable
and lowercase with hyphens where appropriate. A capability is optional: simple
services should not need placeholder handlers.

Each optional executable in `commands/` can have a matching `[[commands]]`
entry in the descriptor with its `name`, short `summary`, optional `details`,
and runnable `examples`. The catalog checks that declared command metadata has
an executable beside it; the shared service CLI renders the metadata and
forwards arguments without maintaining a per-service help dictionary.

Contributors should define the service's defaults, shared dependencies, public
route metadata, setup and validation needs, generated secret relationships,
launch preparation, supported lifecycle operations, and exact
removal/preservation scope in the service contribution. Health check
capabilities are not implemented yet. Put reusable execution, user prompts, confirmation,
platform routing, and output formatting in the common workflows. Follow
[Command and Service Ownership](command-architecture.md) for the boundary and
compatibility rules.

The catalog centralizes Compose-backed service discovery, and each current
service must have a valid `opendock.toml`. Descriptors declare setup fields,
shared configuration dependencies, runtime dependencies, and any enabled
removal contract. Hermes implements version 1 runtime, prepare, secret, and
validation capabilities; Mastodon and Supabase implement service-specific
secret and validation capabilities. The common setup engine reads the same
field schema for all services. Only capabilities implemented by the current
contract may be declared; unsupported declarations fail during catalog
loading. When adding a service, include a descriptor and its setup schema even
if the descriptor has no custom capability.

Runtime cleanup and code registration are separate lifecycles. `purge
<service>` removes declared runtime resources while keeping the service
available in the checkout. Uninstalling an extension's package code is a
separate operation and must refuse while runtime resources remain. Removing a
contribution from OpenDock source must not silently delete runtime data on a
user's host.

Removal is available only for installed services whose descriptors declare an
audited removal contract. Declare service-owned bind data paths, private config
files, extra images, and labeled
non-Compose containers under `[removal]` in the service descriptor. Private
config files are backed up with restrictive permissions before deletion.
Declared `preserve_paths` inside removable directories are listed and retained.
Every orphan container must be tied to a declared data path and is selected
only when its mount source is inside that path. The common remover handles
Compose containers, volumes, configured images, routes, and the service's
private configuration. Removal contracts must account for shared database
objects, user data, backups, and preservation boundaries. Only installed
services with an audited removal declaration are enabled. Uptime Kuma stores
application data in a Compose named volume. Declaration and static validation do not
replace the isolated-host acceptance pass below. Optional package descriptors
own their own service-specific removal details in OpenDock-Services.

The final acceptance pass must use a clean, isolated host. For each service,
configure and launch it, repeat launch to confirm idempotence, inspect its
purge plan, purge it, and
confirm that its declared resources are gone while shared infrastructure and
unrelated services remain. This full pass remains outstanding; removal support
must not be described as end-to-end verified until it passes.

Common target groups:

```text
all       infra + gateway + every service
services  every service under services/
infra     shared infrastructure only
gateway   Caddy only
<name>    one service resolved by ID from the catalog
```

Purpose-based service groups live in:

```text
services/groups.conf
```

The format is intentionally small:

```text
media: immich jellyfin
publishing: wordpress mastodon
communication: mattermost
```

Group names are target aliases for multiple services. They are supported by setup, check-config, secrets, up/start/restart/build/config, down/stop/ps/pull, launch, and publish. Service names win if a service and group ever share the same name. Commands with service-specific behavior, such as logs and sync, should stay single-target unless there is a clear UX reason to broaden them.

`up`, `start`, `restart`, `build`, and `config` stay close to Docker Compose behavior for the requested target.

`setup` is the interactive OpenDock setup workflow. It reads platform defaults from `config/**/*.env.default` and installed service defaults from each registered package release's `.env.default`. It asks only for user-facing values, keeps existing values when the user presses Enter, fills missing generated secrets without printing them, and writes private overrides only when needed. Changed files are backed up under `backups/config/`. Existing `common.env`, `infra/.env`, `gateway/.env`, and old `config/services/*.env` installations are migrated to their owners on initialization, with restrictive backups retained.

`launch <hostname>` is the primary workflow. It resolves exactly one route,
starts `infra` and the mapped Docker service when the route is Docker-backed, or
creates only the shared Docker network for a static route (not the database
containers), then reloads/starts Caddy and publishes that hostname. The legacy service/group form remains supported; a service-name
launch must fail before starting containers if that service maps to multiple
hostnames. The target is required: use `launch all` explicitly to start the full
installed stack; omitting the target must show usage instead of selecting all.

After starting services, `launch` runs the optional `post_launch` capability
only when the service descriptor declares it. The service's `opendock.py`
handler owns the operation; Mastodon and Supabase currently delegate to their
existing service-local helper scripts.

Do not create initial app accounts in OpenDock when the service provides a first-run web setup flow. WordPress, Jellyfin, Uptime Kuma, and Mattermost follow this model. Use post-launch account bootstrap only when a service cannot be reached or administered after launch without an initial account created outside the web UI.

`service` is the namespace for service-specific manual commands:

```sh
./opendock service <service>
./opendock service <service> <command>
```

Commands live beside the resolved service definition under `commands/<command>` and must be executable. `./opendock service <service>` lists executable commands for that service. The dispatcher passes `OPENDOCK_ROOT`, `OPENDOCK_SERVICE`, `OPENDOCK_SERVICE_COMMAND`, and `OPENDOCK_SERVICE_DIR` to the command process.

Supabase Edge Function user secrets follow the same local-template pattern as
other OpenDock configuration. `./opendock launch supabase` creates the ignored
`services/supabase/functions.env` from `functions.env.example`; the optional
`./opendock service supabase functions-secrets` command reports configured names and
application instructions without revealing values. Keep this file outside
`config/functions/`, because that source directory is also mounted in Studio.

WordPress multisite is exposed as `./opendock service wordpress multisite`. It enables subdirectory multisite only. Before changing files or the database, it requires confirmation unless `YES=1` is set, backs up `wp-config.php`, `.htaccess`, and the WordPress MariaDB database, runs WP-CLI conversion with `WORDPRESS_CLI_IMAGE`, patches the Apache `.htaccess` rules used by the WordPress container, and restarts WordPress.

Keep service-specific workflows under `./opendock service <service> <command>` instead of adding new top-level CLI commands. `./opendock list services` lists installed services; `./opendock up services` starts them all.

## Config Validation

`scripts/check-config.py` validates local configuration before Docker Compose starts or renders services.

For the interactive setup design background, see `docs/smart-config.md`.

Manual commands:

```sh
./opendock check-config
./opendock check-config services
./opendock check-config immich
```

Automatic validation runs before:

```text
up
start
restart
build
config
launch
```

`launch` calls `up`, so it reuses the same validation layer instead of running a duplicate check. When `launch` starts `infra` as a prerequisite, that prerequisite is validated through the same path.

Validation rules:

- `config/core.env` must contain the main stack domain.
- Compose variables without defaults, such as `${IMMICH_DB_PASSWORD}`, are required.
- Compose variables with defaults, such as `${JELLYFIN_SUBDOMAIN:-media}`, are optional.
- Required values that are empty fail validation.
- Required secret-like values ending in `PASSWORD`, `SECRET`, `TOKEN`, or `KEY` fail validation if they still match their corresponding tracked defaults (`.env.default` or legacy `.env.example`).
- `STACK_DOMAIN=example.com` is treated as a placeholder.

Automatic validation uses quiet mode and prints only failures. Manual `./opendock check-config` also prints optional values that will use defaults.

Secret generation rules:

- `./opendock check-config` is read-only and never changes files.
- `./opendock setup [target]` interactively fills user-facing values and generated secrets.
- `./opendock secrets [target]` fills generated passwords and app secrets in their owner-specific configuration files.
- `./opendock up <target>`, `./opendock up services`, and
  `./opendock launch <target>` run the same generator before validation.
- Existing real values are kept. Empty or placeholder values are generated.
- Before a configuration file is changed, its previous version is backed up under `backups/config/`.
- Do not auto-generate external values such as `STACK_DOMAIN`, Cloudflare tokens, tunnel IDs, or SMTP credentials.
- Initial login passwords, such as `NEXTCLOUD_ADMIN_PASSWORD`, may be generated, but docs must explain where to find them and whether changing the value later affects an installed app.

Mail setup rules:

- `./opendock setup mail` stores shared outbound SMTP relay values in `config/shared/mail.env`.
- `config/shared/mail.toml` declares shared mail keys and setup prompts;
  `config/shared/database.toml` declares shared database keys and dependency
  groups. Their matching `.env.default` files contain tracked values, while
  the common setup workflow reads the TOML metadata.
- Services opt into the optional prompt through
  `setup.optional_config = ["mail"]` in their descriptor. Declining does not
  block setup or startup and is remembered; `./opendock setup mail` remains the
  explicit way to configure the relay later.
- Map common SMTP values only into services that support official environment-based core mail configuration.
- Do not configure plugin-based, UI-only, or notification-provider mail settings from OpenDock.

## Domain Convention

The stack uses one default domain to derive service hostnames until a custom
route map is initialized:

```env
STACK_DOMAIN=example.com
```

Routable services declare their subdomain setting key and Caddy handler in
`services/bundles/<service>/opendock.toml`. The default value remains in that service's
`.env.default`. For example:

```env
WORDPRESS_SUBDOMAIN=blog
N8N_SUBDOMAIN=n8n
UPTIME_KUMA_SUBDOMAIN=uptime
HOMEPAGE_SUBDOMAIN=home
NEXTCLOUD_SUBDOMAIN=cloud
IMMICH_SUBDOMAIN=photos
JELLYFIN_SUBDOMAIN=media
MASTODON_SUBDOMAIN=social
```

The descriptor links a service ID to its setting explicitly; the setting name
does not need to follow a name-derived rule. For example:

```text
homepage    -> HOMEPAGE_SUBDOMAIN
immich      -> IMMICH_SUBDOMAIN
jellyfin    -> JELLYFIN_SUBDOMAIN
mastodon    -> MASTODON_SUBDOMAIN
n8n         -> N8N_SUBDOMAIN
nextcloud   -> NEXTCLOUD_SUBDOMAIN
uptime-kuma -> UPTIME_KUMA_SUBDOMAIN
wordpress   -> WORDPRESS_SUBDOMAIN
```

If a subdomain value is absent, the resolver falls back to the service ID.

`./opendock setup` configures the primary domain and does not ask about optional
routes. Users manage hostname mappings with `./opendock route show`,
`./opendock route add <hostname> <service|static>`, and
`./opendock route remove <hostname>`. `./opendock launch <hostname>` starts the mapped
Docker service or applies a static route. Static roots use
`static-sites/<hostname>/` and are served directly by Caddy. Cloudflare
publishing locates the zone containing each hostname. All zones used by one
Tunnel must be in the same Cloudflare account, and the API token needs DNS
permissions for each zone. The launch target is required; use `all` explicitly
to start every installed service. `./opendock launch <service>` remains
available; if that service has multiple hostnames, it fails with hostname
commands to avoid ambiguity.

## Caddy Route Convention

Route handlers live in each installed package under `routing/` and are declared
by the service descriptor. Package handlers live beside the package
descriptor and are mounted read-only into Caddy from the active extension store.
Reference snippets use `.caddy.example` and are not loaded by Caddy.

Each public service declares `routing.handler_file` and
`routing.caddy_handler` in `opendock.toml`.

Each service Caddy file defines a reusable upstream snippet. Hostname site blocks
are generated from `domains.conf` (or the default domain convention when that
file is absent):

```caddy
(service_proxy) {
    import common_proxy
    import security_headers
    import block_bots

    reverse_proxy service:port
}

```

The generated file creates HTTP-only host blocks for every mapping. Cloudflare
Tunnel terminates public TLS; its connector reaches Caddy over HTTP.

Caddy globally disables automatic HTTP-to-HTTPS redirects. OpenDock publishes
managed Tunnel hostnames to the configured Caddy origin, which defaults to
`http://localhost:80`. Publishing updates managed hostname rules to that
origin. Public browser HTTP-to-HTTPS redirects are expected to happen at
Cloudflare.

Direct public Caddy exposure without Cloudflare Tunnel is outside the supported
OpenDock path. OpenDock routes public hostnames through its configured
Cloudflare Tunnel.

## Publish Discovery

When `domains.conf` is absent, `./opendock publish` uses default routes from
the installed service catalog. Routable packages declare:

```text
services/extensions/installed.toml
services/extensions/<service-id>/releases/<version>/opendock.toml
services/extensions/<service-id>/releases/<version>/routing/<handler-file>
```

The internal route map connects hostnames to Docker services or the matching
`static-sites/<hostname>/` root. Users manage it with `./opendock route` commands and
Cloudflare publishing follows the resolved route list.

## Cloudflare Sync

`scripts/publish-cloudflare.py` performs Cloudflare sync.

Inputs:

```text
config/
config/cloudflare.env
services/extensions/installed.toml
services/extensions/<service-id>/releases/<version>/compose.yml
services/extensions/<service-id>/releases/<version>/routing/*
```

Required Cloudflare env values:

```env
CLOUDFLARE_API_TOKEN=
CLOUDFLARE_TUNNEL_ID=
```

The script locates the Cloudflare zone containing each service hostname. When
multiple zones are used, they must belong to the account that owns the Tunnel.

Sync behavior:

- GET tunnel configuration
- merge required hostname ingress rules
- preserve existing ingress rules
- keep or create a final fallback rule
- PUT tunnel configuration only when changed
- create missing DNS CNAME records
- stop on DNS conflicts

## Multi-Container Services

Some services cannot be expressed as a single container. Supabase, for example, requires a dedicated PostgreSQL image with extensions, an API gateway, an auth service, a storage service, and several supporting components that must run together.

For multi-container services:

- Keep all containers in a single `services/bundles/<name>/compose.yml`.
- Use a shared `shared-net` external network so all containers can reach each other and the Caddy gateway.
- Pin versions in `services/bundles/<name>/.env.default` as with single-container services.
- Route all public traffic through one gateway container (e.g. Kong) rather than exposing each container through Caddy separately.
- The Caddy route file should proxy to the internal gateway container only.

### Kong API Gateway Pattern

When a service uses Kong as an internal gateway (db-less declarative mode), Kong's configuration file (`kong.yml`) may reference environment variables for runtime-injected values such as dashboard credentials.

Kong does not natively expand environment variables inside its declarative config file. To inject values at container start without writing credentials to a committed file, use a shell entrypoint script:

```
services/bundles/<name>/config/kong-entrypoint.sh   # mounted read-only into the container
services/bundles/<name>/config/kong.yml             # template with $PLACEHOLDER markers
```

The entrypoint script uses `awk` to substitute placeholders with container environment variable values, writes the result to `/tmp/kong.yml` (writable by the Kong user), then starts Kong with `KONG_DECLARATIVE_CONFIG=/tmp/kong.yml`.

Key points:

- Write substituted output to `/tmp/` — Kong's working directories (`/var/lib/kong/`, `/usr/local/kong/`) are owned by root and not writable by the `kong` user at runtime.
- Use literal `$PLACEHOLDER` markers and environment-aware `awk` substitution rather than `eval echo`, which strips YAML string quotes and corrupts the format version field.
- Keep generated credential alphabets YAML-safe and quote placeholders where arbitrary user input is allowed.
- The entrypoint script must be executable (`chmod +x`) before being committed.
- `KONG_PLUGINS` must explicitly list all plugins used across all routes, including `basic-auth`, even if only one route uses it.

## Adding A Service

Add service files:

```text
services/bundles/<service-name>/compose.yml
services/bundles/<service-name>/.env.default
services/bundles/<service-name>/README.md
services/bundles/<service-name>/routing/<handler-file>
```

Add defaults to `services/bundles/<service>/.env.default` and keep local overrides in the ignored `services/bundles/<service>/.env`:

```env
PLEX_SUBDOMAIN=media
```

Then verify:

```sh
./opendock list services
./opendock check-config <service-name>
./opendock publish <service-name>
./opendock config <service-name>
```

## Storage Policy

Use Docker named volumes when the data is app-internal and users do not need direct file access.

Examples:

```text
n8n
nextcloud
uptime-kuma
```

Use bind mounts when users are expected to inspect, upload, backup, or modify files directly.

Example:

```text
immich/data/library
jellyfin/media
wordpress/data/webroot
```

For large user libraries, declare a service-specific host path setting with a
checkout-local default. Users can replace it with an absolute directory on a
mounted disk through `./opendock setup <service>`. Keep `create_host_path: false`
in Compose so an unavailable mount cannot be replaced by an empty directory,
validate the path before launch, and show the configured path in the service's
removal plan. Keep databases on local storage unless the upstream service
explicitly supports another location.

This is opt-in per service, not a requirement for every persistent mount.
WordPress' selectable path covers the entire webroot, including core, plugins,
themes, and uploads. Hermes' `/opt/data` includes credentials and sessions,
while its sandbox workspace also participates in nested Docker bind mounts and
container cleanup; leave those on their current storage until that separate
contract is designed. `create_host_path: false` prevents Compose from creating
a missing path but does not detect an unmounted disk when its mount-point
directory remains present.

Services should use shared MariaDB, PostgreSQL, or Redis when the generic infrastructure is enough. Some services require app-specific infrastructure instead. For example, Immich uses the shared Redis service, but runs its own PostgreSQL image because Immich requires vector extensions that are not part of a generic PostgreSQL service.

## Image Policy

- Avoid `latest`.
- Keep image versions in tracked `.env.default` files, not in `compose.yml`.
- Prefer Ubuntu Noble based images by default.
- Use Alpine only when the image has clear advantages and low compatibility risk.

## Validation Checklist

Before merging service or routing changes:

```sh
./opendock list
./opendock list services
./opendock list groups
./opendock publish
git diff --check
```

For changed Compose projects:

```sh
./opendock config <service-name>
```

OpenDock resolves tracked platform defaults, their private owner files, then
the selected service's `services/bundles/<service>/.env.default` and private
`services/bundles/<service>/.env` override, followed by process environment. Direct
`docker compose config` calls must pass the applicable files in that same order.

For Caddy changes:

```sh
docker run --rm -v "$PWD/gateway/caddy:/etc/caddy:ro" caddy:2 caddy validate --config /etc/caddy/Caddyfile
```
