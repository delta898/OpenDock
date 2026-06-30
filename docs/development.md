# Development Notes

This document describes the conventions used by OpenDock. It is intended for maintainers and advanced users who want to add or modify services.

## Design Goals

- Services should be easy to start from the repository root.
- Adding a service should not require editing the Makefile.
- A single `STACK_DOMAIN` should produce predictable service hostnames.
- Public routes should be discoverable from repository structure.
- Cloudflare Tunnel is the default public exposure layer.
- Beginner-facing setup should stay small: `common.env`, optional `cloudflare.env`, then `make launch`.

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
make
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
- create or edit `common.env`
- create or edit `cloudflare.env`
- create a Cloudflare Tunnel
- run `make launch`

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

## Makefile Target Discovery

The Makefile discovers services at runtime by scanning:

```text
services/*/compose.yml
```

This is why new services do not need Makefile changes.

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
```

Group names are target aliases for multiple services. They are supported by setup, check-config, secrets, up/start/restart/build/config, down/stop/ps/pull, launch, and publish. Service names win if a service and group ever share the same name. Commands with service-specific behavior, such as logs and sync, should stay single-target unless there is a clear UX reason to broaden them.

`up`, `start`, `restart`, `build`, and `config` stay close to Docker Compose behavior for the requested target.

`setup` is the interactive OpenDock setup workflow. It creates `common.env` when missing, asks only for user-facing values, keeps existing values when the user presses Enter, fills missing generated secrets without printing them, and backs up `common.env` before mutation.

`launch` is a higher-level workflow. For `all`, it starts every target in order. For a single service, `services`, or `gateway`, it first starts `infra` so the external `shared-net` network exists, then starts the requested target, reloads or starts Caddy, and publishes matching routes.

After starting services, `launch` runs service-owned post-launch hooks named `services/<service>/opendock-post-launch.py` when present. Keep service-specific bootstrap logic inside those service directories instead of adding new top-level Make targets.

`action` is the shared entry point for service-specific manual workflows:

```sh
make action <service>
make action <service> <action>
```

Actions live at `services/<service>/actions/<action>` and must be executable. `make action <service>` lists executable actions for that service. The dispatcher passes `OPENDOCK_ROOT`, `OPENDOCK_SERVICE`, and `OPENDOCK_ACTION` to the action process.

WordPress multisite is exposed as `make action wordpress multisite`. It enables subdirectory multisite only. Before changing files or the database, it requires confirmation unless `YES=1` is set, backs up `wp-config.php`, `.htaccess`, and the WordPress MariaDB database, runs WP-CLI conversion with `WORDPRESS_CLI_IMAGE`, patches the Apache `.htaccess` rules used by the WordPress container, and restarts WordPress.

`make wp-multisite` remains as a temporary deprecated shortcut for backward compatibility. New service-specific workflows should use `make action <service> <action>` instead of adding new top-level Make targets.

## Config Validation

`scripts/check-config.py` validates local configuration before Docker Compose starts or renders services.

For the interactive setup design background, see `docs/smart-config.md`.

Manual commands:

```sh
make check-config
make check-config services
make check-config immich
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

- `common.env` must exist.
- Compose variables without defaults, such as `${IMMICH_DB_PASSWORD}`, are required.
- Compose variables with defaults, such as `${JELLYFIN_SUBDOMAIN:-media}`, are optional.
- Required values that are empty fail validation.
- Required secret-like values ending in `PASSWORD`, `SECRET`, `TOKEN`, or `KEY` fail validation if they still match the placeholder in `common.env.example`.
- `STACK_DOMAIN=example.com` is treated as a placeholder.

Automatic validation uses quiet mode and prints only failures. Manual `make check-config` also prints optional values that will use defaults.

Secret generation rules:

- `make check-config` is read-only and never changes files.
- `make setup [target]` interactively fills user-facing values and generated secrets.
- `make secrets [target]` fills generated passwords and app secrets in `common.env`.
- `make up`, `make services`, and `make launch` run the same generator before validation.
- Existing real values are kept. Empty or placeholder values are generated.
- Before `common.env` is changed, the previous file is backed up under `backups/common-env/`.
- Do not auto-generate external values such as `STACK_DOMAIN`, Cloudflare tokens, tunnel IDs, or SMTP credentials.
- Initial login passwords, such as `NEXTCLOUD_ADMIN_PASSWORD`, may be generated, but docs must explain where to find them and whether changing `common.env` later affects an installed app.

Mail setup rules:

- `make setup mail` stores common outbound SMTP relay values in `common.env`.
- Map common SMTP values only into services that support official environment-based core mail configuration.
- Do not configure plugin-based, UI-only, or notification-provider mail settings from OpenDock.

## Domain Convention

The stack assumes one main domain:

```env
STACK_DOMAIN=example.com
```

Each service may define a subdomain variable in `common.env`:

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

If a subdomain variable is absent, publish automation falls back to the service directory name.

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

The Caddy route should use the shared domain convention and the reusable snippets from `global.caddy`:

```caddy
(service_proxy) {
    import common_proxy
    import security_headers
    import block_bots

    reverse_proxy service:port
}

http://{$SERVICE_SUBDOMAIN:service}.{$STACK_DOMAIN:localhost} {
    import service_proxy
}

https://{$SERVICE_SUBDOMAIN:service}.{$STACK_DOMAIN:localhost} {
    import service_proxy
}
```

The HTTP block supports Cloudflare Tunnel origin traffic. The HTTPS block keeps direct TLS routing possible for advanced manual setups.

Caddy globally disables automatic HTTP-to-HTTPS redirects. Cloudflare Tunnel uses `http://localhost:80` as its origin, and origin-side HTTPS redirects can create redirect loops. Public browser HTTP-to-HTTPS redirects are expected to happen at Cloudflare.

For direct Caddy exposure without Cloudflare Tunnel, remove the `auto_https disable_redirects` block from `gateway/caddy/Caddyfile` and forward both port 80 and 443 to the server. This restores Caddy's default HTTP-to-HTTPS redirect behavior.

## Publish Discovery

`make publish` publishes only services that have both:

```text
services/<service-name>/compose.yml
gateway/caddy/conf.d/<service-name>.caddy
```

This keeps the publish list structure-driven and avoids service mappings in scripts or the Makefile.

## Cloudflare Sync

`scripts/publish-cloudflare.py` performs Cloudflare sync.

Inputs:

```text
common.env
cloudflare.env
services/*/compose.yml
gateway/caddy/conf.d/*.caddy
```

Required Cloudflare env values:

```env
CLOUDFLARE_API_TOKEN=
CLOUDFLARE_TUNNEL_ID=
```

The script uses `STACK_DOMAIN` to look up the Cloudflare zone and account automatically.

Sync behavior:

- GET tunnel configuration
- merge required hostname ingress rules
- preserve existing ingress rules
- keep or create a final fallback rule
- PUT tunnel configuration only when changed
- create missing DNS CNAME records
- stop on DNS conflicts

## Adding A Service

Add service files:

```text
services/<service-name>/compose.yml
services/<service-name>/.env
services/<service-name>/README.md
gateway/caddy/conf.d/<service-name>.caddy
```

Add a default subdomain to `common.env.example` if the desired public name differs from the service directory name:

```env
PLEX_SUBDOMAIN=media
```

Then verify:

```sh
make list services
make check-config <service-name>
make publish <service-name>
docker compose --project-directory services/<service-name> --env-file common.env.example --env-file services/<service-name>/.env -f services/<service-name>/compose.yml config
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
make list
make list services
make list groups
make publish
git diff --check
```

For changed Compose projects:

```sh
docker compose --project-directory <dir> --env-file common.env.example --env-file <dir>/.env -f <dir>/compose.yml config
```

For Caddy changes:

```sh
docker run --rm -v "$PWD/gateway/caddy:/etc/caddy:ro" caddy:2 caddy validate --config /etc/caddy/Caddyfile
```
