# OpenDock

A Docker Compose based home server stack with sensible defaults, Caddy routing, and Cloudflare Tunnel publishing.

The goal is simple: set one main domain, run one command, and get a small but useful home server online.

OpenDock assumes Cloudflare Tunnel as the default public exposure layer. Cloudflare handles public DNS, public HTTPS, and browser HTTP-to-HTTPS redirects. Caddy runs as the internal gateway for routing Cloudflare Tunnel origin traffic to Docker services.

## Included Services

```text
home.<your-domain>    -> Homepage
blog.<your-domain>    -> WordPress
cloud.<your-domain>   -> Nextcloud
photos.<your-domain>  -> Immich
media.<your-domain>   -> Jellyfin
social.<your-domain>  -> Mastodon
n8n.<your-domain>     -> n8n
uptime.<your-domain>  -> Uptime Kuma
```

Shared infrastructure:

```text
MariaDB
PostgreSQL
Redis
Caddy
```

## Requirements

- Ubuntu Server or another Linux host
- A domain managed by Cloudflare
- A Cloudflare Tunnel connected to this server

OpenDock includes an Ubuntu bootstrap script that installs prerequisites and clones this repository to `~/OpenDock` by default.

## Setup Overview

For a typical Cloudflare Tunnel setup:

1. Create or log in to a Cloudflare account.
2. Add your domain to Cloudflare and update its nameservers.
3. Create a Cloudflare Tunnel and connect it to your home server.
4. Create a Cloudflare API token.
5. Run the Ubuntu bootstrap script.
6. Copy example env files to real local env files.
7. Edit the required domain config.
8. Edit optional Cloudflare config: API token and tunnel ID.
9. Run `make launch`.

After that, Docker services are started, Cloudflare routes are synced, DNS records are prepared, and public URLs are printed.

## Quick Start

On a fresh Ubuntu Server 24.04 or newer host, install prerequisites and clone OpenDock to `~/OpenDock`:

```sh
curl -fsSL https://raw.githubusercontent.com/delta898/OpenDock/main/scripts/bootstrap-ubuntu.sh | bash
```

The bootstrap script installs base packages from Ubuntu repositories:

```text
git
make
curl
ca-certificates
```

If Docker and Docker Compose are not already installed, it also installs:

```text
docker.io
docker-compose-v2
```

It enables Docker, adds the current user to the `docker` group, and clones OpenDock to `~/OpenDock`. If the user was newly added to that group, log out and log back in before running Docker commands.

To inspect the script before running it:

```sh
curl -fsSL https://raw.githubusercontent.com/delta898/OpenDock/main/scripts/bootstrap-ubuntu.sh -o bootstrap-ubuntu.sh
less bootstrap-ubuntu.sh
bash bootstrap-ubuntu.sh
```

After the default bootstrap completes, enter the cloned repository:

```sh
cd ~/OpenDock
```

If you want to install prerequisites without cloning the repository:

```sh
curl -fsSL https://raw.githubusercontent.com/delta898/OpenDock/main/scripts/bootstrap-ubuntu.sh | bash -s -- --no-clone
```

Then clone manually when you are ready:

```sh
git clone https://github.com/delta898/OpenDock.git ~/OpenDock
cd ~/OpenDock
```

Create and review the local env file:

```sh
make setup
```

`make setup` asks for values that need your intent, such as the main domain, and keeps existing values when you press Enter. It also generates local passwords and app secrets without printing them.

If you prefer to edit by hand, copy the example file and set at least the main domain:

```sh
cp common.env.example common.env
nano common.env
```

OpenDock also generates local passwords and app secrets automatically before `make up` and `make launch`. Existing real values in `common.env` are kept. If `common.env` must be updated, the previous file is backed up under `backups/common-env/`.

You can also generate values explicitly:

```sh
make secrets
make secrets nextcloud
```

Nextcloud's generated admin password is the initial login password for the first installation. The value is stored in `NEXTCLOUD_ADMIN_PASSWORD` in `common.env`; changing it later does not reset an already installed Nextcloud account.

The default subdomains are already defined in `common.env.example`:

```env
HOMEPAGE_SUBDOMAIN=home
WORDPRESS_SUBDOMAIN=blog
NEXTCLOUD_SUBDOMAIN=cloud
IMMICH_SUBDOMAIN=photos
JELLYFIN_SUBDOMAIN=media
MASTODON_SUBDOMAIN=social
N8N_SUBDOMAIN=n8n
UPTIME_KUMA_SUBDOMAIN=uptime
```

Start the stack:

```sh
make launch
```

`make launch` starts the Docker services and then publishes public routes if `cloudflare.env` exists. When launching one service, it also starts `infra` first so the shared Docker network and shared infrastructure are ready:

```sh
make launch wordpress
```

Before starting services, OpenDock fills generated secrets and checks `common.env` for required values. This helps catch missing external settings after `git pull` adds a new service.

## Cloudflare Publishing

Cloudflare Tunnel is the default public entrypoint for this stack.

Without `cloudflare.env`, `make publish` only prints the routes it would publish. With `cloudflare.env`, it syncs Cloudflare Tunnel public hostnames and DNS records automatically.

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
cloud.<your-domain>   -> http://localhost:80
photos.<your-domain>  -> http://localhost:80
media.<your-domain>   -> http://localhost:80
social.<your-domain>  -> http://localhost:80
n8n.<your-domain>     -> http://localhost:80
uptime.<your-domain>  -> http://localhost:80
```

Set each Cloudflare Tunnel public hostname's Service URL to `http://localhost:80`. Public users should still open `https://<service>.<your-domain>`.

## Without Cloudflare Tunnel

Cloudflare Tunnel is the default supported public exposure layer for this stack. If you choose to expose Caddy directly with port forwarding instead, Caddy becomes the public edge.

In that case:

- forward port 80 and 443 to the server
- remove the `auto_https disable_redirects` block from `gateway/caddy/Caddyfile`
- open services with `https://<service>.<your-domain>`

Removing that block lets Caddy restore its default HTTP-to-HTTPS redirects. Do not remove it when using Cloudflare Tunnel, because Tunnel origin traffic uses `http://localhost:80` and can enter redirect loops.

## Common Commands

List available targets:

```sh
make list
make list services
```

Check local configuration:

```sh
make check-config
make check-config immich
```

`check-config` runs automatically before commands that start or render services:

```text
up
start
restart
build
config
launch
```

`make check-config` is read-only. Commands that start services generate missing local passwords and app secrets first, then run the same validation.

Review or update local setup interactively:

```sh
make setup
make setup mail
make setup mastodon
```

`make setup mail` stores common SMTP relay settings in `common.env`. OpenDock maps those values only into services that support official environment-based mail configuration, currently Mastodon and n8n.

Generate local secrets manually:

```sh
make secrets
make secrets wordpress
make secrets mastodon
```

Start services:

```sh
make up infra
make up gateway
make up services
make up wordpress
```

`make up <target>` is a thin Docker Compose wrapper for that target. It does not start prerequisites for you.

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
make launch wordpress
```

`make launch <target>` is the higher-level workflow: it prepares `infra` when needed, starts the target, reloads or starts the gateway, and publishes the target routes.

Enable WordPress subdirectory multisite:

```sh
make wp-multisite
```

This command converts the launched WordPress site into subdirectory multisite mode, for example `https://blog.example.com/site-name/`. It prints a warning and asks for confirmation before changing anything. Before conversion, it backs up `wp-config.php`, `.htaccess`, and the WordPress MariaDB database under `services/wordpress/backups/`.

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

When you update the repository with `git pull`, compare new values in `common.env.example` with your local `common.env`. Missing optional subdomain values use sensible defaults, and missing generated secrets are filled automatically before service startup. External values such as `STACK_DOMAIN` and Cloudflare credentials still require user input.

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
    ├── immich/
    ├── jellyfin/
    ├── mastodon/
    ├── n8n/
    ├── nextcloud/
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
SYNC_TEST_PATH=/home/user/OpenDock
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
