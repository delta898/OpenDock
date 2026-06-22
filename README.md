# DockerPackages

A Docker Compose based home server stack with sensible defaults, Caddy routing, and optional Cloudflare Tunnel publishing.

The goal is simple: set one main domain, fill in a few secrets, run one command, and get a small but useful home server online.

## Included Services

```text
home.<your-domain>    -> Homepage
blog.<your-domain>    -> WordPress
n8n.<your-domain>     -> n8n
uptime.<your-domain>  -> Uptime Kuma
```

Shared infrastructure:

```text
MariaDB
Redis
Caddy
```

## Requirements

- Ubuntu Server or another Linux host
- Docker with the Compose plugin
- `make`
- A domain managed by Cloudflare, if you want automatic public publishing
- A Cloudflare Tunnel already connected to this server, if you use Cloudflare Tunnel

## Setup Overview

For a typical Cloudflare Tunnel setup:

1. Create or log in to a Cloudflare account.
2. Add your domain to Cloudflare and update its nameservers.
3. Create a Cloudflare Tunnel and connect it to your home server.
4. Create a Cloudflare API token.
5. Clone this repository.
6. Copy example env files to real local env files.
7. Edit required config: domain and passwords.
8. Edit optional Cloudflare config: API token and tunnel ID.
9. Run `make launch`.

After that, Docker services are started, Cloudflare routes are synced, DNS records are prepared, and public URLs are printed.

## Quick Start

Clone the repository:

```sh
git clone https://github.com/delta898/DockerPackages.git
cd DockerPackages
```

Create the required local env file:

```sh
cp common.env.example common.env
```

Edit `common.env`:

```env
STACK_DOMAIN=example.com

MARIADB_ROOT_PASSWORD=change-root-password
WORDPRESS_DB_PASSWORD=change-wordpress-db-password
```

The default subdomains are already defined in `common.env.example`:

```env
HOMEPAGE_SUBDOMAIN=home
WORDPRESS_SUBDOMAIN=blog
N8N_SUBDOMAIN=n8n
UPTIME_KUMA_SUBDOMAIN=uptime
```

Start the stack:

```sh
make launch
```

`make launch` starts the Docker services and then publishes public routes if `cloudflare.env` exists.

## Cloudflare Publishing

Cloudflare automation is optional. Without `cloudflare.env`, `make publish` only prints the routes it would publish.

To enable Cloudflare sync:

```sh
cp cloudflare.env.example cloudflare.env
```

Edit `cloudflare.env`:

```env
CLOUDFLARE_API_TOKEN=
CLOUDFLARE_TUNNEL_ID=
```

Create the API token with permissions that can read the zone, edit DNS records, and edit Cloudflare Tunnel configuration. In Cloudflare's token UI, this usually means:

```text
Zone / Zone / Read
Zone / DNS / Edit
Account / Cloudflare Tunnel / Edit
```

Then run:

```sh
make publish
```

`make publish` uses `STACK_DOMAIN` to find the Cloudflare zone and account automatically. It then:

- adds or updates Cloudflare Tunnel public hostnames
- creates missing DNS CNAME records
- preserves existing tunnel rules
- stops on DNS conflicts instead of overwriting unrelated records

All public hostnames point to the same local Caddy gateway:

```text
home.<your-domain>    -> http://localhost:80
blog.<your-domain>    -> http://localhost:80
n8n.<your-domain>     -> http://localhost:80
uptime.<your-domain>  -> http://localhost:80
```

## Common Commands

List available targets:

```sh
make list
make list services
```

Start services:

```sh
make up infra
make up gateway
make up services
make up wordpress
```

Publish routes:

```sh
make publish
make publish services
make publish n8n
```

Start and publish:

```sh
make launch
make launch services
make launch homepage
```

Inspect or stop:

```sh
make ps all
make logs n8n
make down services
make down gateway
```

## Configuration Files

Local files ignored by Git:

```text
common.env       required local stack settings and secrets
cloudflare.env   optional Cloudflare API settings
.sync.env        optional rsync test-machine settings
```

Committed defaults:

```text
common.env.example
cloudflare.env.example
infra/.env
gateway/.env
services/*/.env
```

## Directory Layout

```text
.
├── infra/
│   └── compose.yml
├── gateway/
│   ├── compose.yml
│   └── caddy/
│       ├── Caddyfile
│       └── conf.d/
└── services/
    ├── homepage/
    ├── n8n/
    ├── uptime-kuma/
    └── wordpress/
```

## Sync To A Test Machine

Copy the example sync config and edit it locally:

```sh
cp .sync.env.example .sync.env
```

Then set your test machine connection:

```env
SYNC_TEST_REMOTE=user@test-host
SYNC_TEST_PATH=/home/user/DockerPackages
```

Preview first:

```sh
make sync-dry-run test
```

Then sync:

```sh
make sync test
```

Runtime data such as `services/*/data/`, `common.env`, `cloudflare.env`, and `.sync.env` is excluded.

## Development

For service conventions, publish automation details, and contribution notes, see [docs/development.md](docs/development.md).
