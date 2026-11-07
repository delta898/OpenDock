# OpenDock

A Docker Compose platform for installing and operating self-hosted services.

OpenDock provides the platform CLI, host bootstrap, shared runtime, and a static
service catalog. Service packages are published separately from the platform.

OpenDock keeps one consistent CLI while services own their application-specific
setup and lifecycle details. See the [command ownership and service extension
guide](docs/command-architecture.md) for maintainers adding capabilities.

There is no bundled-service product category. Services are distributed as
packages from OpenDock-Services through a static catalog. The platform does
not access that private source repository. The development catalog, package
setup, and first launch path are connected. The Uptime Kuma pilot has reached
its first-run database screen through the public route; completing application
setup and checking final app readiness remain outside the verified scope. See
[Product Architecture](docs/product-distribution.md)
for the target and implementation status.

The platform checkout still contains legacy service files during migration;
they are not the product model for new services. Shared platform components
include:

```text
MariaDB
PostgreSQL
Redis
Caddy
```

## Requirements

- Ubuntu Server 24.04 or newer, or macOS.
- An internet connection, `curl`, and Bash to run the bootstrap script.
- On Ubuntu, a user account with `sudo` access. Bootstrap installs Python 3 and
  Docker Engine with Compose v2 if they are missing.
- On macOS, Python 3.11 or newer and Docker Desktop (or another Docker
  compatible runtime with Compose v2). Start the runtime before installing.
- For public access, a domain managed by Cloudflare and a Tunnel connector
  that can reach this server's Caddy origin.
- `rsync` and SSH are needed only if you use remote sync.

Git is not required.

## Bootstrap

Run this command on the machine where you want to host OpenDock:

```sh
curl -fsSL https://raw.githubusercontent.com/delta898/OpenDock/main/scripts/bootstrap.sh | bash
```

Bootstrap prepares Docker, then installs the OpenDock runtime under
`~/OpenDock`. It installs only the files needed to run OpenDock; it does not
copy Git metadata, CI files, tests, or developer documentation. Service
packages are downloaded separately when you install or launch a service.

On Ubuntu, bootstrap installs Python 3 and, when needed, Docker Engine and
Compose v2. If it adds your account to the `docker` group, log out and back in
before running Docker commands without `sudo`.

On macOS, install Python 3.11+ and Docker Desktop before running bootstrap. If
Docker Desktop is installed but stopped, bootstrap opens it and waits for it to
start. Complete any first-run setup in Docker Desktop yourself.

### Cloudflare Tunnel

OpenDock needs two different Cloudflare credentials for public hosting. They
do different jobs, so create both before setup. The API token goes into
`./opendock setup cloudflare`; the connector token is used by bootstrap. Do not
paste one in place of the other.

#### 1. Create an API token for OpenDock

In Cloudflare, open **My Profile → API Tokens → Create Token → Create Custom
Token**. Give it a name such as `OpenDock DNS and Tunnel Sync`, then add these
permissions:

| Resource | Permission | Why OpenDock needs it |
| --- | --- | --- |
| Account → Cloudflare Tunnel | Edit | Read and update Tunnel hostname routes |
| Zone → DNS | Edit | Create or update DNS records for OpenDock hostnames |
| Zone → Zone | Read | Find the zone for each hostname |

Under **Account Resources**, select only the account that owns the Tunnel.
Under **Zone Resources**, select only the domain zones OpenDock will manage.
Review the summary, create the token, and copy it when Cloudflare shows it.
Cloudflare displays the token secret only once. Do not use your Global API Key.
See Cloudflare's [API token creation guide](https://developers.cloudflare.com/fundamentals/api/get-started/create-token/)
and [permission reference](https://developers.cloudflare.com/fundamentals/api/reference/permissions/).

#### 2. Create or select a remotely managed Tunnel

In Cloudflare, open **Networking → Tunnels** and create a Tunnel, or select an
existing remotely managed Tunnel. Record its Tunnel ID. On the Tunnel's
**Overview** tab, select **Add a replica** and copy the token from the displayed
`cloudflared` command; do not run that command. This connector token is
different from the API token above. Anyone who has the connector token can run
a connector for that Tunnel, so keep it private. See Cloudflare's [Tunnel token
guide](https://developers.cloudflare.com/tunnel/reference/tunnel-tokens/).

During bootstrap, paste the connector token at the hidden prompt. If you do not
have it yet, choose **No**; bootstrap prints the exact file and setting to use
later. After bootstrap, configure the primary domain and API credentials:

```sh
cd ~/OpenDock
./opendock setup
./opendock setup cloudflare
```

Enter the API token and Tunnel ID when prompted. OpenDock stores them with the
connector token in the private `config/cloudflare.env` file.

### Install and launch a service

Search the service catalog, then launch a service. Launch installs it if needed
and guides you through its first setup:

```sh
./opendock search <words>
./opendock launch <service-id>
```

The default install directory is `~/OpenDock`. To choose another directory:

```sh
curl -fsSL https://raw.githubusercontent.com/delta898/OpenDock/main/scripts/bootstrap.sh | bash -s -- --dir "$HOME/opendock"
```

To view all options without making changes:

```sh
curl -fsSL https://raw.githubusercontent.com/delta898/OpenDock/main/scripts/bootstrap.sh | bash -s -- --help
```

You can also inspect the [bootstrap script](scripts/bootstrap.sh).

## Development package flow

Set the public catalog base URL in private `config/core.env` as
`OPENDOCK_DEV_CATALOG_BASE_URL`, then use the development wrapper:

```sh
./dev_opendock update
./dev_opendock search uptime
./dev_opendock install uptime-kuma
./dev_opendock launch n8n-v2
```

The wrapper fixes these commands to the `dev` catalog. `search` uses the local
catalog cache and refreshes it automatically when it is missing, invalid, or
more than 24 hours old. `update` always forces a refresh. `install` verifies
the package checksum before placing the release under `services/extensions/`;
installation does not configure or launch the service. Select the production
catalog with `./opendock update --environment prod` or
`./opendock search n8n --environment prod`.

For a service that is not installed yet, `launch <service>` refreshes the
selected catalog, installs the matching package, opens its setup flow, and
continues into launch. `./dev_opendock launch <service>` selects the dev
catalog for this first-use flow; `./opendock launch <service>` uses prod.

Uptime Kuma `0.1.0` has been published to the development catalog. The user
confirmed update, search, install, setup, and launch on Linux. Infra and Uptime
Kuma containers became healthy, and the public route displayed Kuma's first-run
database selection page. Choosing/configuring the database is the user's
application setup; OpenDock does not create a Kuma database or account. Wizard
completion, post-setup application readiness, purge, and multi-domain isolation
remain unverified.

## Hostname routing

OpenDock routes public hostnames to static files, installed OpenDock services,
or applications running outside OpenDock. The common command is:

```text
./opendock route add <type> <hostname> [<target>]
```

Examples and target reachability requirements are documented in
[`docs/routes.md`](docs/routes.md). After adding a route, run
`./opendock launch <hostname>` to apply it to Caddy and publish it through
Cloudflare Tunnel. External targets must be reachable from the Caddy container.

### Legacy platform setup reference

For the current Cloudflare Tunnel setup:

1. Put the domain in Cloudflare and connect a Tunnel connector that can reach
   this server's Caddy HTTP origin.
2. Run `./opendock setup` to set the primary domain.
3. Run `./opendock setup cloudflare` for automatic Tunnel and DNS publication.
4. Install a service package from the catalog, then use `./opendock setup
   <service>` or `./opendock launch <service>`.

For another hostname, add a typed route such as
`./opendock route add service app.example.org n8n-v3` or
`./opendock route add static docs.example.org`, then run
`./opendock launch <hostname>`. Static routes serve files from
`static-sites/<hostname>/`.

Run `./opendock help` to see available commands. GNU Make is only needed if
you use the older `make ...` compatibility commands.

The former in-repository service workflow was:

```sh
./opendock list
./opendock setup
./opendock launch homepage
```

This workflow is retained as a reference for the existing platform code. It is
not the new service installation workflow.

Legacy in-repository service settings were created by `./opendock setup`. To edit them by hand, use the
owner-specific local files after setup:

```sh
nano config/core.env
nano services/bundles/homepage/.env
nano services/bundles/uptime-kuma/.env
```

OpenDock also generates local passwords and app secrets automatically before `./opendock up` and `./opendock launch`. Existing values are kept. Before a config file changes, its previous version is backed up under `backups/config/`. Existing installations using `common.env` are migrated automatically the next time OpenDock setup or startup initializes configuration; the original file is retained in that backup directory.

You can also generate values explicitly:

```sh
./opendock secrets
```

Generated bundle secrets are stored in the corresponding private bundle `.env` file.

Default subdomains are defined in each bundled service's tracked defaults:

```env
HOMEPAGE_SUBDOMAIN=home
UPTIME_KUMA_SUBDOMAIN=uptime
```

Extension defaults are supplied by their package and appear after installation.

The default route list uses these subdomains under `STACK_DOMAIN`. You can
inspect it with `./opendock route show`. Additional hostnames need an explicit
mapping to an installed service:

```sh
./opendock route add service home2.example.com homepage
./opendock launch home2.example.com
./opendock route add static docs.example.org
./opendock launch docs.example.org
```

Service targets use their registered service ID. For a static route,
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

Start the default Homepage service. OpenDock derives its hostname from the
primary domain and `HOMEPAGE_SUBDOMAIN`, so no `route add` is needed:

```sh
./opendock launch home.primary.com
```

For custom or secondary hostnames, add the mapping first. Static content is
managed by the user; OpenDock applies its serving and publishing route:

```sh
./opendock route add static docs.primary.com
./opendock launch docs.primary.com
```

Before starting services, OpenDock fills generated secrets and checks the
layered configuration for required values. This helps catch missing external
settings after `git pull` adds a new service.

## External media storage

Optional packages may expose service-owned storage paths in their descriptors.
Their setup and removal documentation becomes available after installing the
package. OpenDock validates configured paths before starting a service.

## Cloudflare Publishing

Cloudflare Tunnel is the default public entrypoint for this stack.

Cloudflare setup is required for OpenDock public routes. The initial
`./opendock setup` configures Cloudflare along with the platform. Public
`launch` checks these settings before changing service state; if needed, it
opens the Cloudflare setup flow. `./opendock setup cloudflare` is also available
to review or repair the settings directly.

```sh
./opendock setup cloudflare
```

Create the API token with permissions that can read the zone, edit DNS records, and edit Cloudflare Tunnel configuration. In Cloudflare's token UI, this usually means:

Step-by-step token, permission, and Tunnel ID instructions are in the [Cloudflare Tunnel setup guide](#cloudflare-tunnel).

```text
Zone / Zone / Read
Zone / DNS / Edit
Account / Cloudflare Tunnel / Edit
```

The connector must also be running and able to reach the OpenDock Caddy gateway.
Then run:

```sh
./opendock publish
```

`./opendock publish` locates the Cloudflare zone containing each configured hostname. It then:

- adds or updates Cloudflare Tunnel public hostnames to use the configured
  Caddy origin
- creates missing DNS CNAME records
- preserves existing tunnel rules
- checks for DNS conflicts before changing Tunnel or DNS state, then stops
  instead of overwriting unrelated records

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

Cloudflare Tunnel hostnames use the configured Caddy origin, which defaults to
`http://localhost:80`. Publishing updates the hostname rule to that origin.
Public users should still open `https://<service>.<your-domain>`.

## Public exposure requirement

OpenDock supports public service routes through Cloudflare Tunnel. Direct
public exposure of Caddy without Cloudflare is not a supported setup path.

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

### Optional email (SMTP)

SMTP is a shared, optional setting. Services that declare support for it offer configuration during setup or first launch. Choose **No** to continue without SMTP; OpenDock remembers the choice, and the service still starts. Email-dependent features may be unavailable until you configure a relay. Supabase keeps its local Inbucket fallback unless you configure an external relay. The currently integrated services are Docmost, Mastodon, Mattermost, n8n, and Supabase.

To configure or change the relay later:

```sh
./opendock setup mail
```

The SMTP values are stored in `config/shared/mail.env`. For command examples and options, run `./opendock setup --help` or `./opendock help`.

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
./opendock launch homepage
./opendock route add static docs.example.com
./opendock launch docs.example.com
```

The service-name form selects that service's default route. Use a hostname when
you have added multiple routes for the same service:

```sh
./opendock launch homepage
```

An unknown hostname fails with instructions to add a route. `route add` records
the mapping and prepares a static web root when needed; `launch` applies the
route to Caddy and publishes it. External routes do not start the upstream.

Service groups are defined in `services/groups.conf`. Use `./opendock list groups` to see the available groups.

Inspect or stop:

```sh
./opendock ps all
./opendock logs uptime-kuma
./opendock down homepage
./opendock down gateway
```

## Configuration Files

Configuration ownership and precedence are documented in [`config/README.md`](config/README.md).

Local files ignored by Git:

```text
config/          private core, infrastructure, shared, service, and Cloudflare settings
.sync.env.toml   optional rsync test-machine settings
infra/.env       legacy defaults, migrated automatically on first use
gateway/.env     legacy defaults, migrated automatically on first use
```

Committed defaults:

```text
config/**/*.env.default
services/extensions/<service-id>/releases/<version>/.env.default
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
    └── extensions/       # installed packages; ignored by Git
archive/                  # local legacy service copy; ignored and inactive
```

Optional service source is maintained in the sibling OpenDock-Services
repository. Previous service directories and their local state are kept in the
gitignored `archive/` folder on this checkout; they are not discovered or
included in repository sync.

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
and local state such as `.git/`, `services/*/data/`, `services/*/backups/`,
installed packages under `services/extensions/`, `static-sites/` contents,
private `config/*.env` files (and the legacy
`common.env` migration input), `.sync.env.toml`,
`*.env` files, `domains.conf`, the generated Caddy routes file, and
`services/supabase/functions.env` are protected on the destination. Local
configuration migration markers under `config/` are also preserved so a later
sync does not repeat one-time migrations. The tracked
`static-sites/README.md` and other committed examples remain deployable.

Other destination-only files are treated as repository files and removed, so
the sync destination should be dedicated to an OpenDock checkout. This also
cleans up stale code from earlier syncs. Use `./opendock sync test --dry-run`
first to review both file transfers and destination-only files that would be
removed.

## Development

The greenfield product target is documented in
[docs/product-distribution.md](docs/product-distribution.md), with detailed
[catalog/package](docs/catalog-and-package-contract.md),
[service capability](docs/service-contract.md), and
[command/instance](docs/command-model.md) contracts. These describe the target
design; current repository docs and commands describe the existing
implementation and are not the new compatibility contract.

For service conventions, see [docs/development.md](docs/development.md) and
[Adding a Service to OpenDock](docs/adding-services.md). To have an AI assistant
prepare a contribution from service-specific inputs, use the
[service contribution meta prompt](docs/prompts/add-service.md).
