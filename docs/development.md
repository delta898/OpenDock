# Development Notes

This document describes the conventions used by OpenDock. It is intended for maintainers and advanced users who want to add or modify services.

## Design Goals

- Services should be easy to start from the repository root.
- Adding a service should not require editing the CLI dispatcher.
- `STACK_DOMAIN` should produce predictable default hostnames; `domains.conf` can map any hostname to a service or static directory.
- Public routes should be discoverable from repository structure.
- Cloudflare Tunnel is the default public exposure layer.
- Beginner-facing setup should stay small: `./opendock setup`, then
  `./opendock launch <hostname>`; Cloudflare is optional.

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
- create or edit `cloudflare.env`
- create a Cloudflare Tunnel
- run `./opendock launch`

This keeps system preparation separate from stack configuration and avoids hiding important security choices from the user.

## Directory Conventions

Core projects live at the repository root:

```text
infra/      shared infrastructure
gateway/    Caddy reverse proxy
```

Application services live under:

```text
services/<service-name>/compose.yml
```

Examples:

```text
services/wordpress/compose.yml
services/n8n/compose.yml
services/homepage/compose.yml
services/nextcloud/compose.yml
services/immich/compose.yml
services/jellyfin/compose.yml
```

## CLI Target Discovery

The CLI discovers services at runtime by scanning:

```text
services/*/compose.yml
```

This is why new services do not need CLI dispatcher changes.

Common target groups:

```text
all       infra + gateway + every service
services  every service under services/
infra     shared infrastructure only
gateway   Caddy only
<name>    one service under services/<name>/
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

`setup` is the interactive OpenDock setup workflow. It reads platform defaults from `config/**/*.env.default`, Hermes defaults from `services/hermes/.env.default`, and defaults for services not yet migrated from `config/services/*.env.example`. It asks only for user-facing values, keeps existing values when the user presses Enter, fills missing generated secrets without printing them, and writes private overrides only when needed. Changed files are backed up under `backups/config/`. Existing `common.env` installations are split into owner files on initialization, with the original retained in the backup directory.

`launch <hostname>` is the primary workflow. It resolves exactly one route,
starts `infra` and the mapped Docker service when the route is Docker-backed, or
creates only the shared Docker network for a static route (not the database
containers), then reloads/starts Caddy and publishes that hostname. The legacy service/group form remains supported; a service-name
launch must fail before starting containers if that service maps to multiple
hostnames. `launch all` remains the compatibility workflow for the full stack.

After starting services, `launch` runs service-owned post-launch hooks named `services/<service>/opendock-post-launch.py` when present. Keep service-specific bootstrap logic inside those service directories instead of adding new top-level Make targets.

Do not create initial app accounts in OpenDock when the service provides a first-run web setup flow. WordPress, Jellyfin, Uptime Kuma, and Mattermost follow this model. Use post-launch account bootstrap only when a service cannot be reached or administered after launch without an initial account created outside the web UI.

`service` is the namespace for service-specific manual commands:

```sh
./opendock service <service>
./opendock service <service> <command>
```

Commands live at `services/<service>/commands/<command>` and must be executable. `./opendock service <service>` lists executable commands for that service. The dispatcher passes `OPENDOCK_ROOT`, `OPENDOCK_SERVICE`, and `OPENDOCK_SERVICE_COMMAND` to the command process.

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
- `./opendock up <target>`, `./opendock up services`, and `./opendock launch` run the same generator before validation.
- Existing real values are kept. Empty or placeholder values are generated.
- Before a configuration file is changed, its previous version is backed up under `backups/config/`.
- Do not auto-generate external values such as `STACK_DOMAIN`, Cloudflare tokens, tunnel IDs, or SMTP credentials.
- Initial login passwords, such as `NEXTCLOUD_ADMIN_PASSWORD`, may be generated, but docs must explain where to find them and whether changing the value later affects an installed app.

Mail setup rules:

- `./opendock setup mail` stores shared outbound SMTP relay values in `config/shared/mail.env`.
- Map common SMTP values only into services that support official environment-based core mail configuration.
- Do not configure plugin-based, UI-only, or notification-provider mail settings from OpenDock.

## Domain Convention

The stack uses one default domain to derive service hostnames until a custom
route map is initialized:

```env
STACK_DOMAIN=example.com
```

Each service may define a subdomain variable in its configuration owner file. Hermes and future migrated services use `services/<service>/.env`; services not yet migrated use `config/services/<service>.env`:

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

The variable name is derived from the service directory name:

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

If a subdomain variable is absent, the default route generator falls back to the service directory name.

`./opendock setup` configures the primary domain and does not ask about optional
routes. Users manage hostname mappings with `./opendock route show`,
`./opendock route add <hostname> <service|static>`, and
`./opendock route remove <hostname>`. `./opendock launch <hostname>` starts the mapped
Docker service or applies a static route. Static roots use
`static-sites/<hostname>/` and are served directly by Caddy. Cloudflare
publishing locates the zone containing each hostname. All zones used by one
Tunnel must be in the same Cloudflare account, and the API token needs DNS
permissions for each zone. The legacy `./opendock launch <service>` form remains
available; if that service has multiple hostnames, it fails with hostname
commands to avoid ambiguity.

## Caddy Route Convention

Active route files live under:

```text
gateway/caddy/conf.d/<service-name>.caddy
```

Reference snippets use `.caddy.example` and are not loaded by Caddy.

Each public service should have:

```text
services/<service-name>/compose.yml
gateway/caddy/conf.d/<service-name>.caddy
```

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

The generated file creates both HTTP and HTTPS host blocks for every mapping.

Caddy globally disables automatic HTTP-to-HTTPS redirects. Cloudflare Tunnel uses `http://localhost:80` as its origin, and origin-side HTTPS redirects can create redirect loops. Public browser HTTP-to-HTTPS redirects are expected to happen at Cloudflare.

For direct Caddy exposure without Cloudflare Tunnel, remove the `auto_https disable_redirects` block from `gateway/caddy/Caddyfile` and forward both port 80 and 443 to the server. This restores Caddy's default HTTP-to-HTTPS redirect behavior.

## Publish Discovery

When `domains.conf` is absent, `./opendock publish` discovers Docker services that have both:

```text
services/<service-name>/compose.yml
gateway/caddy/conf.d/<service-name>.caddy
```

The internal route map connects hostnames to Docker services or the matching
`static-sites/<hostname>/` root. Users manage it with `./opendock route` commands and
Cloudflare publishing follows the resolved route list.

## Cloudflare Sync

`scripts/publish-cloudflare.py` performs Cloudflare sync.

Inputs:

```text
config/
cloudflare.env
services/*/compose.yml
gateway/caddy/conf.d/*.caddy
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

- Keep all containers in a single `services/<name>/compose.yml`.
- Use a shared `shared-net` external network so all containers can reach each other and the Caddy gateway.
- Pin versions in `services/<name>/.env` as with single-container services.
- Route all public traffic through one gateway container (e.g. Kong) rather than exposing each container through Caddy separately.
- The Caddy route file should proxy to the internal gateway container only.

### Kong API Gateway Pattern

When a service uses Kong as an internal gateway (db-less declarative mode), Kong's configuration file (`kong.yml`) may reference environment variables for runtime-injected values such as dashboard credentials.

Kong does not natively expand environment variables inside its declarative config file. To inject values at container start without writing credentials to a committed file, use a shell entrypoint script:

```
services/<name>/config/kong-entrypoint.sh   # mounted read-only into the container
services/<name>/config/kong.yml             # template with $PLACEHOLDER markers
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
services/<service-name>/compose.yml
services/<service-name>/.env
services/<service-name>/README.md
gateway/caddy/conf.d/<service-name>.caddy
```

For a new or migrated service, add defaults to `services/<service>/.env.default` and keep local overrides in the ignored `services/<service>/.env`. For a service not yet migrated, add a default subdomain to `config/services/<service>.env.example`:

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

Services should use shared MariaDB, PostgreSQL, or Redis when the generic infrastructure is enough. Some services require app-specific infrastructure instead. For example, Immich uses the shared Redis service, but runs its own PostgreSQL image because Immich requires vector extensions that are not part of a generic PostgreSQL service.

## Image Policy

- Avoid `latest`.
- Keep image versions in `.env`, not in `compose.yml`.
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
the selected service defaults and private override, followed by process
environment. Hermes uses `services/hermes/.env.default` and
`services/hermes/.env`; unmigrated services retain their legacy example and
tracked runtime `.env` inputs. Direct `docker compose config` calls must pass
the applicable files in that same order.

For Caddy changes:

```sh
docker run --rm -v "$PWD/gateway/caddy:/etc/caddy:ro" caddy:2 caddy validate --config /etc/caddy/Caddyfile
```
