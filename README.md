# DockerPackages

Personal Docker Compose workspace for shared infrastructure, gateway services, and application services.

## Structure

```text
.
├── infra/
│   └── compose.yml
├── gateway/
│   └── caddy/
└── services/
    ├── homepage/
    ├── n8n/
    ├── uptime-kuma/
    └── wordpress/
```

## Usage

```sh
make list
make list services
make up infra
make up gateway
make up wordpress
make up n8n
make up uptime-kuma
make up homepage
make ps infra
make logs infra
make down infra
```

Service compose files follow this convention:

```text
services/<service-name>/compose.yml
```

Then they can be controlled from the project root:

```sh
make up wordpress
make logs wordpress
make down wordpress
make up n8n
make logs n8n
make up uptime-kuma
make logs uptime-kuma
make up homepage
make logs homepage
```

Gateway route files follow this convention:

```text
gateway/caddy/conf.d/<service-name>.caddy
```

Default services committed to this repository should have their active gateway routes in `gateway/caddy/conf.d/`. Reference-only snippets use the `.caddy.example` suffix.

## Stack Domain

This stack assumes one main domain and publishes default services as subdomains:

```text
STACK_DOMAIN=example.com

blog.example.com -> WordPress
n8n.example.com  -> n8n
uptime.example.com -> Uptime Kuma
home.example.com -> Homepage
```

Copy and edit the common env file before running services:

```sh
cp common.env.example common.env
```

Set your main domain and passwords:

```sh
STACK_DOMAIN=gongzza.com
MARIADB_ROOT_PASSWORD=change-root-password
WORDPRESS_DB_PASSWORD=change-wordpress-db-password
```

The default service subdomains are also in `common.env`:

```sh
WORDPRESS_SUBDOMAIN=blog
N8N_SUBDOMAIN=n8n
UPTIME_KUMA_SUBDOMAIN=uptime
HOMEPAGE_SUBDOMAIN=home
```

You usually only need to change `STACK_DOMAIN`.

## First Run

Start the stack:

```sh
make up infra
make up wordpress
make up n8n
make up uptime-kuma
make up homepage
make up gateway
```

Then open the default services:

```text
https://blog.<your-domain>
https://n8n.<your-domain>
https://uptime.<your-domain>
https://home.<your-domain>
```

If you use Cloudflare Tunnel, route each public hostname to the same local gateway:

```text
blog.<your-domain> -> http://localhost:80
n8n.<your-domain>  -> http://localhost:80
uptime.<your-domain> -> http://localhost:80
home.<your-domain> -> http://localhost:80
```

If you use direct port forwarding instead, forward both ports 80 and 443 to the server. The same Caddy routes support both Cloudflare Tunnel HTTP origin traffic and direct HTTPS traffic.

After changing `common.env` or a Caddy route file, recreate the affected containers:

```sh
make down n8n
make down gateway
make up n8n
make up gateway
```

## Sync To Test Machine

Copy the example sync config and edit it locally:

```sh
cp .sync.env.example .sync.env
```

Then set your test machine connection:

```sh
SYNC_TEST_REMOTE=user@test-host
SYNC_TEST_PATH=/home/user/DockerPackages
```

Preview the rsync changes first:

```sh
make sync-dry-run test
```

Then sync:

```sh
make sync test
```

The real `.sync.env` file is intentionally ignored by Git. Sync excludes local runtime data such as `services/*/data/`, including the WordPress webroot.

## Environment

Edit `common.env` locally. It contains the stack domain, shared defaults, and sensitive values, so it is intentionally ignored by Git.

- `common.env` contains shared or sensitive values.
- Each directory `.env` is committed with non-sensitive defaults for that compose project.
