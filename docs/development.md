# Development Notes

This document describes the conventions used by DockerPackages. It is intended for maintainers and advanced users who want to add or modify services.

## Design Goals

- Services should be easy to start from the repository root.
- Adding a service should not require editing the Makefile.
- A single `STACK_DOMAIN` should produce predictable service hostnames.
- Public routes should be discoverable from repository structure.
- Cloudflare Tunnel is the default public exposure layer.
- Beginner-facing setup should stay small: `common.env`, optional `cloudflare.env`, then `make launch`.

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

## Config Validation

`scripts/check-config.py` validates local configuration before Docker Compose starts or renders services.

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

`launch` calls `up`, so it reuses the same validation layer instead of running a duplicate check.

Validation rules:

- `common.env` must exist.
- Compose variables without defaults, such as `${IMMICH_DB_PASSWORD}`, are required.
- Compose variables with defaults, such as `${JELLYFIN_SUBDOMAIN:-media}`, are optional.
- Required values that are empty fail validation.
- Required secret-like values ending in `PASSWORD`, `SECRET`, `TOKEN`, or `KEY` fail validation if they still match the placeholder in `common.env.example`.
- `STACK_DOMAIN=example.com` is treated as a placeholder.

Automatic validation uses quiet mode and prints only failures. Manual `make check-config` also prints optional values that will use defaults.

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
```

The variable name is derived from the service directory name:

```text
homepage    -> HOMEPAGE_SUBDOMAIN
immich      -> IMMICH_SUBDOMAIN
jellyfin    -> JELLYFIN_SUBDOMAIN
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

Some services require app-specific infrastructure instead of shared infrastructure. For example, Immich uses the shared Redis service, but runs its own PostgreSQL image because Immich requires vector extensions that are not part of a generic PostgreSQL service.

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
