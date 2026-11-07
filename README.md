# OpenDock

A Docker Compose platform for installing and operating self-hosted services.

OpenDock provides the platform CLI, host bootstrap, shared runtime, and a static
service catalog. Service packages are published separately from the platform.

OpenDock keeps one consistent CLI while services own their application-specific
setup and lifecycle details. See the [command ownership and service extension
guide](docs/command-architecture.md) for maintainers adding capabilities.

There is no bundled-service product category. Services are distributed as
packages from OpenDock-Services through a static catalog. The platform does
not access the source repository. See [Product Architecture](docs/product-distribution.md)
for the product boundary, distribution model, and implementation status.

Shared platform components include:

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
If `~/OpenDock` already contains a managed OpenDock runtime, bootstrap refreshes
its runtime files and defaults while preserving private configuration and
installed services. It leaves a Git checkout untouched. An existing empty
directory can be used as the install target. For any other non-empty directory,
choose a different path with `--dir`; bootstrap will not merge files into an
unrelated directory.

On Ubuntu, bootstrap installs Python 3 and, when needed, Docker Engine and
Compose v2. If it adds your account to the `docker` group, log out and back in
before running Docker commands without `sudo`.

On macOS, install Python 3.11+ and Docker Desktop before running bootstrap. If
Docker Desktop is installed but stopped, bootstrap opens it and waits for it to
start. Complete any first-run setup in Docker Desktop yourself.

### Cloudflare Tunnel

Cloudflare is the main external setup for public hosting. OpenDock needs two
tokens and one Tunnel ID across two steps; the names are easy to mix up. Follow the
[Cloudflare Tunnel setup guide](https://github.com/delta898/OpenDock#cloudflare-tunnel)
as you go:

| Value | Enter it in | What it does |
| --- | --- | --- |
| Tunnel token | Bootstrap | Authenticates `cloudflared` to your remotely managed Tunnel |
| Cloudflare API token | `./opendock setup` | Lets OpenDock update DNS and Tunnel routes |
| Tunnel ID | `./opendock setup` | Identifies which remotely managed Tunnel OpenDock updates |

The Tunnel token and API token are different credentials with different jobs;
the Tunnel ID is an identifier, not a token. Bootstrap can store the Tunnel
token without echoing it; setup prompts for the API token privately. One
Tunnel/connector carries traffic for all OpenDock services through Caddy; you
do not create a separate Tunnel token for each service.

#### 1. Create or select a remotely managed Tunnel and copy its token

In Cloudflare, open **Networking → Tunnels** and select **Create Tunnel**.
Name it, then select **Create Tunnel**. On the **Setup Environment** screen,
choose the environment only to display the matching connector command; OpenDock
will run the connector for you, so do not install or run Cloudflare's command.
The Tunnel ID appears on this screen. In **Install and Run**, copy the long
`eyJ...` value after `--token` in the displayed command. That value is the
**Tunnel token**; it is not the Tunnel ID.

If the Tunnel already exists or you leave this screen, open **Networking →
Tunnels → <your tunnel> → Overview → Add a replica** and copy the token from
the displayed `cloudflared` command. You do not need to create a separate
Tunnel token: Cloudflare provides it as part of the connector command. Keep it
private because anyone holding it can run a connector for that Tunnel. See
Cloudflare's [Tunnel token guide](https://developers.cloudflare.com/tunnel/reference/tunnel-tokens/).

#### 2. Create an API token for OpenDock

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

During bootstrap, paste the Tunnel token at the hidden prompt. If you do not
have it yet, choose **No**; bootstrap prints the exact file and setting to use
later. After bootstrap, run setup once to configure the primary domain, API
token, and Tunnel ID shown when you created the Tunnel. To review only the
Cloudflare values later, run
`./opendock setup cloudflare`:

```sh
cd ~/OpenDock
./opendock setup
```

OpenDock stores both tokens and the Tunnel ID in the private
`config/cloudflare.env` file.

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

Use the development wrapper to select the dev catalog automatically:

```sh
./dev_opendock update
./dev_opendock search <words>
./dev_opendock install <service-id>
./dev_opendock launch <service-id>
```

The wrapper fixes these commands to the `dev` catalog. `search` uses the local
catalog cache and refreshes it automatically when it is missing, invalid, or
more than 24 hours old. `update` always forces a refresh. `install` verifies
the package checksum before placing the release under `services/extensions/`;
installation does not configure or launch the service. Select the production
catalog with `./opendock update --environment prod` or
`./opendock search <words> --environment prod`.

For a service that is not installed yet, `launch <service>` refreshes the
selected catalog, installs the matching package, opens its setup flow, and
continues into launch. `./dev_opendock launch <service>` selects the dev
catalog for this first-use flow; `./opendock launch <service>` uses prod.

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

Run `./opendock help` to see available commands. For another hostname, add a
typed route such as `./opendock route add service app.example.org <service-id>`
or `./opendock route add static docs.example.org`, then run
`./opendock launch <hostname>`. Static routes serve files from
`static-sites/<hostname>/`.

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

Each public hostname points to the local Caddy gateway:

```text
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
./opendock info <service-id>
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
./opendock check-config <service-id>
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
./opendock setup <service-id>
```

### Optional email (SMTP)

SMTP is a shared, optional setting. Services that declare support for it offer configuration during setup or first launch. Choose **No** to continue without SMTP; OpenDock remembers the choice, and the service still starts. Email-dependent features may be unavailable until you configure a relay.

To configure or change the relay later:

```sh
./opendock setup mail
```

The SMTP values are stored in `config/shared/mail.env`. For command examples and options, run `./opendock setup --help` or `./opendock help`.

Run a service-specific command:

```sh
./opendock list services
./opendock invoke <service-id>
./opendock invoke <service-id> <command>
```

`./opendock invoke <service-id>` lists commands provided by the installed
package. Service commands stay with their package instead of expanding the
shared command set.

Start services:

```sh
./opendock up infra
./opendock up gateway
./opendock up services
./opendock up <service-id>
```

`./opendock up <target>` is a thin Docker Compose wrapper for that target. It does not start prerequisites for you.

Publish routes:

```sh
./opendock publish
./opendock publish services
./opendock publish <service-id>
```

Launch by the default service name or by an explicitly mapped hostname:

```sh
./opendock launch <service-id>
./opendock route add static docs.example.com
./opendock launch docs.example.com
```

The service-name form selects that service's default route. Use a hostname when
you have added multiple routes for the same service:

```sh
./opendock launch <service-id>
```

An unknown hostname fails with instructions to add a route. `route add` records
the mapping and prepares a static web root when needed; `launch` applies the
route to Caddy and publishes it. External routes do not start the upstream.

Service groups are defined in `services/groups.conf`. Use `./opendock list groups` to see the available groups.

Inspect or stop:

```sh
./opendock ps all
./opendock logs <service-id>
./opendock down <service-id>
./opendock down gateway
```

## Configuration Files

Configuration ownership and precedence are documented in [`config/README.md`](config/README.md).

Local files ignored by Git:

```text
config/          private core, infrastructure, shared, service, and Cloudflare settings
.sync.env.toml   optional rsync test-machine settings
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
```

Service source is maintained in the separate OpenDock-Services repository.
OpenDock installs package releases into `services/extensions/` from the
catalog.

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

For platform development conventions, see [docs/development.md](docs/development.md)
and the linked architecture contracts. Service integrations are maintained in
the separate OpenDock-Services repository.
