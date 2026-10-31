# OpenDock

A Docker Compose based home server stack with sensible defaults, Caddy routing, and Cloudflare Tunnel publishing.

The goal is simple: set a default domain, run one command, and get a small but useful home server online.

OpenDock assumes Cloudflare Tunnel as the default public exposure layer. Cloudflare handles public DNS, public HTTPS, and browser HTTP-to-HTTPS redirects. Caddy runs as the internal gateway for routing Cloudflare Tunnel origin traffic to Docker services.

## Included Services

```text
home.<your-domain>    -> Homepage
blog.<your-domain>    -> WordPress
cloud.<your-domain>   -> Nextcloud
photos.<your-domain>  -> Immich
media.<your-domain>   -> Jellyfin
social.<your-domain>  -> Mastodon
chat.<your-domain>    -> Mattermost
supabase.<your-domain> -> Supabase
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

- Linux or macOS with Python 3 and Docker Compose
- rsync and SSH for remote sync
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
6. Run `./opendock setup` to configure the primary domain and generate secrets.
7. Configure optional Cloudflare credentials in `cloudflare.env`.
8. Run `./opendock launch <hostname>` (for example, `./opendock launch blog.example.com`).

That hostname's Docker service is started (or its static route is applied),
Cloudflare is synced when configured, and the public URL is printed.

## Quick Start

On a fresh Ubuntu Server 24.04 or newer host, install prerequisites and clone OpenDock to `~/OpenDock`:

```sh
curl -fsSL https://raw.githubusercontent.com/delta898/OpenDock/main/scripts/bootstrap-ubuntu.sh | bash
```

The bootstrap script installs base packages from Ubuntu repositories:

```text
git
python3
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

On macOS, install Python 3 and Docker Desktop (with Docker Compose), then clone
the repository. OpenDock uses the same `./opendock` commands on Linux and macOS.
Run `./opendock help` to see available commands. GNU Make is only needed if you
use the older `make ...` compatibility commands.

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
./opendock setup
```

`./opendock setup` asks for values that need your intent, such as the main domain, and keeps existing values when you press Enter. It also generates local passwords and app secrets without printing them.

If you prefer to edit by hand, copy the example file and set at least the main domain:

```sh
cp common.env.example common.env
nano common.env
```

OpenDock also generates local passwords and app secrets automatically before `./opendock up` and `./opendock launch`. Existing real values in `common.env` are kept. If `common.env` must be updated, the previous file is backed up under `backups/common-env/`.

You can also generate values explicitly:

```sh
./opendock secrets
./opendock secrets nextcloud
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
MATTERMOST_SUBDOMAIN=chat
SUPABASE_SUBDOMAIN=supabase
N8N_SUBDOMAIN=n8n
UPTIME_KUMA_SUBDOMAIN=uptime
```

The default route list uses these subdomains under `STACK_DOMAIN`. Start a
service by its public hostname. Add extra hostnames with `./opendock route`:

```sh
./opendock route show
./opendock route add blog2.example.com wordpress
./opendock route add docs.example.org static
./opendock launch docs.example.org
./opendock route remove docs.example.org
```

Docker targets use their service name. Static routes serve files from
`static-sites/<hostname>/`; OpenDock creates that directory when the route is
added. Caddy serves files directly without a separate runtime. `./opendock launch
<hostname>` starts the mapped Docker service or, for a static route, prints the
web root and applies Caddy plus Cloudflare routing. The user places static
content in the printed directory. All mapped Cloudflare zones must belong to
the Tunnel's account, and the API token needs access to each zone.

`./opendock route remove <hostname>` removes that route from OpenDock and Caddy and,
when Cloudflare credentials are configured, removes the Tunnel entry plus only
a DNS CNAME pointing to this Tunnel. Unrelated DNS records are preserved.
Static files are preserved. `./opendock launch <service>` is
still supported for compatibility; prefer hostname-based launch for new usage.

`domains.conf` and `static-sites/` are host-owned configuration and content, so
the general `./opendock sync` code deployment preserves them on the remote server.
Create the route map and deploy static files on the server.

Start the default WordPress hostname (replace the domain with the value from
`./opendock setup`):

```sh
./opendock launch blog.primary.com
```

`./opendock launch <hostname>` starts the mapped Docker service, reloads Caddy, and
publishes the hostname if `cloudflare.env` exists. For a static route, it prints
the web root and applies routing without starting a Docker service. The legacy
`./opendock launch <service>` form remains available for compatibility.

```sh
./opendock route add docs.primary.com static
./opendock launch docs.primary.com
```

Before starting services, OpenDock fills generated secrets and checks `common.env` for required values. This helps catch missing external settings after `git pull` adds a new service.

## Cloudflare Publishing

Cloudflare Tunnel is the default public entrypoint for this stack.

Without `cloudflare.env`, `./opendock publish` only prints the routes it would publish. With `cloudflare.env`, it syncs Cloudflare Tunnel public hostnames and DNS records automatically.

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
./opendock publish
```

`./opendock publish` locates the Cloudflare zone containing each configured hostname. It then:

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
chat.<your-domain>    -> http://localhost:80
supabase.<your-domain> -> http://localhost:80
n8n.<your-domain>     -> http://localhost:80
uptime.<your-domain>  -> http://localhost:80
<any-mapped-domain>   -> http://localhost:80
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
./opendock list
./opendock list services
./opendock list groups
```

Check local configuration:

```sh
./opendock check-config
./opendock check-config immich
./opendock check-config media
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

`./opendock check-config` is read-only. Commands that start services generate missing local passwords and app secrets first, then run the same validation.

Review or update local setup interactively:

```sh
./opendock setup
./opendock setup mail
./opendock setup mastodon
./opendock setup mattermost
./opendock setup media
```

`./opendock setup mail` stores common SMTP relay settings in `common.env`. OpenDock maps those values only into services that support official environment-based mail configuration, currently Mastodon, Mattermost, and n8n.

Run a service-specific action:

```sh
./opendock action supabase api-keys
./opendock action supabase functions-secrets
./opendock action wordpress
./opendock action wordpress multisite
```

`./opendock action <service>` lists available actions for that service. Actions are for service-specific setup helpers that do not belong in the shared command set.
The Supabase API-key action prints only the client-safe publishable key and
keeps all elevated keys hidden. The Functions action creates or inspects the
local Edge Function secrets file without printing its values; a normal
`./opendock launch supabase` also creates the empty, usable file automatically.

Generate local secrets manually:

```sh
./opendock secrets
./opendock secrets wordpress
./opendock secrets mastodon
./opendock secrets media
```

Start services:

```sh
./opendock up infra
./opendock up gateway
./opendock up services
./opendock up wordpress
./opendock up media
```

`./opendock up <target>` is a thin Docker Compose wrapper for that target. It does not start prerequisites for you.

Publish routes:

```sh
./opendock publish
./opendock publish services
./opendock publish n8n
./opendock publish media
```

Hostname-first launch:

```sh
./opendock launch blog.example.com
./opendock route add docs.example.com static
./opendock launch docs.example.com
```

The legacy service/group form remains available for compatibility:

```sh
./opendock launch wordpress
./opendock launch media
```

Prefer hostnames for new usage. A legacy service launch fails if that service
maps to multiple hostnames; launch the intended hostname instead.

Service groups are defined in `services/groups.conf`. Groups are convenience aliases for multiple services, for example `media` expands to Immich and Jellyfin. Use `./opendock list groups` to see the available groups.

Enable WordPress subdirectory multisite:

```sh
./opendock action wordpress multisite
```

This command converts the launched WordPress site into subdirectory multisite mode, for example `https://blog.example.com/site-name/`. It prints a warning and asks for confirmation before changing anything. Before conversion, it backs up `wp-config.php`, `.htaccess`, and the WordPress MariaDB database under `services/wordpress/backups/`.

The legacy shortcut `./opendock wp-multisite` is still available temporarily, but it is deprecated.

Inspect or stop:

```sh
./opendock ps all
./opendock logs n8n
./opendock down services
./opendock down gateway
```

The WordPress service includes practical PHP defaults for media, theme, and plugin uploads: a 64 MB per-file limit, a 72 MB POST limit, a 256 MB PHP memory limit, and a 300-second processing window. No manual `php.ini` setup is required.

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
    ├── mattermost/
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
./opendock sync test --dry-run
```

Then sync:

```sh
./opendock sync test
```

Runtime data and local secrets such as `services/*/data/`, `common.env`,
`cloudflare.env`, `.sync.env`, and `services/supabase/functions.env` are
excluded. Their committed example files remain available on the destination.

## Development

For service conventions, publish automation details, and contribution notes, see [docs/development.md](docs/development.md).
