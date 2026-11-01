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
hermes.<your-domain>  -> Hermes Agent dashboard
```

Shared infrastructure:

```text
MariaDB
PostgreSQL
Redis
Caddy
```

## Requirements

- Linux or macOS with Python 3.11+ and Docker Compose
- rsync and SSH for remote sync
- For public hosting: a domain managed by Cloudflare and a Cloudflare Tunnel
  connected to this server

OpenDock includes an Ubuntu bootstrap script that installs prerequisites and clones this repository to `~/OpenDock` by default.

## How OpenDock Routes Traffic

OpenDock connects a **hostname** to a **target**. A target is either a Docker
service registered in OpenDock, such as `wordpress`, or the special target
`static` for files served by Caddy.

```text
blog.example.com  -> wordpress (Docker service)
docs.example.com  -> static    (files in static-sites/docs.example.com/)
```

There are two kinds of routes:

- **Default routes** are derived from the primary domain and each service's
  default subdomain. For example, `STACK_DOMAIN=example.com` and
  `WORDPRESS_SUBDOMAIN=blog` provide `blog.example.com -> wordpress` without
  running `route add`.
- **Additional routes** are stored in the host-local `domains.conf` file. Add
  one explicitly with `./opendock route add <hostname> <service|static>`.

`launch` accepts either a service name or a hostname.
`./opendock launch wordpress` starts the service at its default hostname.
`./opendock launch blog.example.com` applies a hostname that already has a
route. An arbitrary hostname is not automatically assigned a service: add its
route first. If one service has multiple hostnames, use the hostname form to
choose which route to publish.

For a static route, OpenDock creates `static-sites/<hostname>/` and configures
Caddy to serve files from it. Put an `index.html` and other site files there;
no Hugo process or separate web-server container is required. `launch` applies
the route and prints the web root, but does not create or upload site content.

`launch` is the managed path: it checks configuration, starts the required
shared infrastructure and service when applicable, updates Caddy, and
publishes configured Cloudflare routes. `up` is a direct Docker Compose
operation for users who want to manage those steps themselves; it does not
start prerequisites or publish routes.

Cloudflare Tunnel is the default public entrypoint. To make publishing
automatic, configure `cloudflare.env` with a token, tunnel ID, and access to
the zones used by your routes. Without those API credentials, OpenDock can
still apply local Caddy routes and print the routes to configure manually in
Cloudflare.

## Setup Overview

For a typical Cloudflare Tunnel setup:

1. Put the domain in Cloudflare and connect a Cloudflare Tunnel to this server.
2. Clone OpenDock and run `./opendock setup` to set the primary domain.
3. Optionally configure Cloudflare API credentials for automatic DNS and
   Tunnel updates; otherwise set up the public hostname in Cloudflare yourself.
4. Run `./opendock launch wordpress` to start the default WordPress route.

For another hostname, first run
`./opendock route add <hostname> <service|static>`, then
`./opendock launch <hostname>`. Static routes serve files from
`static-sites/<hostname>/`.

## Quick Start

On a fresh Ubuntu Server 24.04 or newer host, install prerequisites and clone OpenDock to `~/OpenDock`:

```sh
curl -fsSL https://raw.githubusercontent.com/delta898/OpenDock/main/scripts/bootstrap-ubuntu.sh | bash
```

The bootstrap script installs base packages from Ubuntu repositories:

```text
git
python3 (3.11 or newer)
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

On macOS, install Python 3.11+ and Docker Desktop (with Docker Compose), then clone
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

The shortest first-run path is:

```sh
./opendock list
./opendock setup
./opendock launch wordpress
```

The first command shows available services. Setup asks for the primary domain;
launching WordPress uses its default `blog` subdomain. Hermes can also be
started with `./opendock launch hermes`; its first launch runs the Hermes model
onboarding if no model has been configured yet.

Local settings are created by `./opendock setup`. To edit them by hand, use the
owner-specific local files after setup:

```sh
nano config/core.env
nano services/wordpress/.env
nano services/hermes/.env
```

OpenDock also generates local passwords and app secrets automatically before `./opendock up` and `./opendock launch`. Existing values are kept. Before a config file changes, its previous version is backed up under `backups/config/`. Existing installations using `common.env` are migrated automatically the next time OpenDock setup or startup initializes configuration; the original file is retained in that backup directory.

You can also generate values explicitly:

```sh
./opendock secrets
./opendock secrets nextcloud
```

Nextcloud's generated admin password is the initial login password for the first installation. The value is stored in `services/nextcloud/.env`; changing it later does not reset an already installed Nextcloud account.

Default subdomains are defined in each service's `services/<service>/.env.default`:

```env
HOMEPAGE_SUBDOMAIN=home
WORDPRESS_SUBDOMAIN=blog
NEXTCLOUD_SUBDOMAIN=cloud
IMMICH_SUBDOMAIN=photos
JELLYFIN_SUBDOMAIN=media
MASTODON_SUBDOMAIN=social
MATTERMOST_SUBDOMAIN=chat
SUPABASE_SUBDOMAIN=supabase
HERMES_SUBDOMAIN=hermes
N8N_SUBDOMAIN=n8n
UPTIME_KUMA_SUBDOMAIN=uptime
```

The default route list uses these subdomains under `STACK_DOMAIN`. You can
inspect it with `./opendock route show`. The default WordPress route is
available immediately after setup; additional hostnames need an explicit
mapping:

```sh
./opendock route add blog2.example.com wordpress
./opendock launch blog2.example.com
./opendock route add docs.example.org static
./opendock launch docs.example.org
```

Docker targets use their registered service name. For a static route,
`route add` creates `static-sites/<hostname>/`; `launch` prints that web root
and applies Caddy plus Cloudflare routing. Place your files in that directory.
All mapped Cloudflare zones must belong to the Tunnel's account, and the API
token needs access to each zone when automatic Cloudflare sync is enabled.

`./opendock route remove <hostname>` removes that route from OpenDock and Caddy and,
when Cloudflare credentials are configured, removes the Tunnel entry plus only
a DNS CNAME pointing to this Tunnel. Unrelated DNS records are preserved.
Static files are preserved. Launching by service name selects its default
hostname; launching by hostname selects a specific route.

`domains.conf` and `static-sites/` are host-owned configuration and content, so
the general `./opendock sync` code deployment preserves them on the remote server.
Create the route map and deploy static files on the server.

Start the default WordPress service. OpenDock derives its hostname from the
primary domain and `WORDPRESS_SUBDOMAIN`, so no `route add` is needed:

```sh
./opendock launch blog.primary.com
```

For custom or secondary hostnames, add the mapping first. Static content is
managed by the user; OpenDock applies its serving and publishing route:

```sh
./opendock route add docs.primary.com static
./opendock launch docs.primary.com
```

Before starting services, OpenDock fills generated secrets and checks the
layered configuration for required values. This helps catch missing external
settings after `git pull` adds a new service.

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

`info` shows OpenDock's product metadata along with configured image tags and
container state:

```sh
./opendock --version
./opendock info
./opendock info wordpress
```

OpenDock's name, current version, description, Python requirement, and project
links are maintained in `pyproject.toml`. The `vMAJOR.MINOR.PATCH` Git tag is
the release marker and must match the `version` field. Push a matching tag (for
example, `v0.1.0`) to run the release workflow; ordinary branch pushes and pull
requests continue to run the CLI CI workflow.

Renovate tracks image and GitHub Actions updates and opens reviewable pull
requests. To enable the Cloud-Hosted GitHub App, follow [docs/renovate.md](docs/renovate.md).

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

`./opendock setup mail` stores shared SMTP relay settings in `config/shared/mail.env`. OpenDock maps those values only into services that support official environment-based mail configuration, currently Mastodon, Mattermost, and n8n.

Run a service-specific command:

```sh
./opendock list services
./opendock service supabase api-keys
./opendock service supabase functions-secrets
./opendock service wordpress
./opendock service wordpress multisite
./opendock service hermes onboard
```

`./opendock service <service>` lists available commands for that service. These commands provide service-specific helpers without adding every special case to the shared command set.
The Supabase API-key command prints only the client-safe publishable key and
keeps all elevated keys hidden. The Functions command creates or inspects the
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

Launch by the default service name or by an explicitly mapped hostname:

```sh
./opendock launch wordpress
./opendock route add docs.example.com static
./opendock launch docs.example.com
```

The service-name form selects that service's default route. Use a hostname when
you have added multiple routes for the same service:

```sh
./opendock launch wordpress
./opendock launch media
```

An unknown hostname fails with instructions to add a route. `route add` only
records the mapping and prepares a static web root; `launch` applies the route
to Caddy and publishes it.

Service groups are defined in `services/groups.conf`. Groups are convenience aliases for multiple services, for example `media` expands to Immich and Jellyfin. Use `./opendock list groups` to see the available groups.

Enable WordPress subdirectory multisite:

```sh
./opendock service wordpress multisite
```

This command converts the launched WordPress site into subdirectory multisite mode, for example `https://blog.example.com/site-name/`. It prints a warning and asks for confirmation before changing anything. Before conversion, it backs up `wp-config.php`, `.htaccess`, and the WordPress MariaDB database under `services/wordpress/backups/`.

Inspect or stop:

```sh
./opendock ps all
./opendock logs n8n
./opendock down services
./opendock down gateway
```

The WordPress service includes practical PHP defaults for media, theme, and plugin uploads: a 64 MB per-file limit, a 72 MB POST limit, a 256 MB PHP memory limit, and a 300-second processing window. No manual `php.ini` setup is required.

## Configuration Files

Configuration ownership and precedence are documented in [`config/README.md`](config/README.md).

Local files ignored by Git:

```text
config/          private core, infrastructure, shared, and service settings
cloudflare.env   optional Cloudflare API settings
.sync.env.toml   optional rsync test-machine settings
infra/.env       legacy defaults, migrated automatically on first use
gateway/.env     legacy defaults, migrated automatically on first use
```

Committed defaults:

```text
config/**/*.env.default
services/*/.env.default
cloudflare.env.example
```

When you update the repository with `git pull`, OpenDock reads updated defaults from tracked `.env.default` files. Missing optional subdomain values use sensible defaults, and missing generated secrets are filled automatically before service startup. External values such as `STACK_DOMAIN` and Cloudflare credentials still require user input.

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
cp .sync.env.toml.example .sync.env.toml
```

Then set the target connection in TOML:

```toml
[targets.test]
remote = "user@test-host"
path = "/home/user/OpenDock"
ssh_port = 22 # optional; defaults to 22
```

Preview first:

```sh
./opendock sync test --dry-run
```

Then sync:

```sh
./opendock sync test
```

Sync mirrors tracked files and non-ignored untracked files from the working tree,
so you can test new files before `git add` or commit. Untracked files ignored by
Git are not sent. Runtime data, backups, static site contents, host configuration,
and local secrets such as `.git/`, `services/*/data/`, `services/*/backups/`,
`static-sites/` contents, private `config/*.env` files (and the legacy
`common.env` migration input), `cloudflare.env`, `.sync.env.toml`,
`*.env` files, `domains.conf`, the generated Caddy routes file, and
`services/supabase/functions.env` are protected on the destination. The tracked
`static-sites/README.md` and other committed examples remain deployable.

Other destination-only files are treated as repository files and removed, so
the sync destination should be dedicated to an OpenDock checkout. This also
cleans up stale code from earlier syncs. Use `./opendock sync test --dry-run`
first to review both file transfers and destination-only files that would be
removed.

## Development

For service conventions, publish automation details, and contribution notes, see [docs/development.md](docs/development.md).
