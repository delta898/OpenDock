# Hermes Agent

Hermes Agent runs as an OpenDock service with its web dashboard routed through
Caddy. Agent terminal, code execution, and file tools use Hermes' Docker
backend, which runs commands in a separate, persistent sandbox container.

## Start Hermes

The shortest first-run path is:

```sh
./opendock launch hermes
```

If the OpenDock domain or Hermes settings are missing, launch prompts for them,
then starts OpenDock's shared infrastructure and runs Hermes' first-run
onboarding when no default model is configured. It skips onboarding on later
launches. The first run asks for the values OpenDock cannot infer, such as your
model provider and credentials.

To review the primary domain first, use `./opendock setup`. For a more
deliberate Hermes setup, `./opendock setup hermes` reviews Hermes' OpenDock
settings and completes the same first-run onboarding; then run
`./opendock launch hermes`.

After onboarding, `./opendock setup hermes` reviews OpenDock-managed values and
skips the Hermes wizard when a default model is already configured. To
intentionally re-run Hermes' interactive provider and integration setup later,
use `./opendock service hermes onboard`. This command also ensures the shared
infrastructure is running.

To completely remove Hermes and start fresh, run `./opendock remove hermes`.
OpenDock shows the resources first and requires typing `REMOVE hermes`. This
removes Hermes containers, its Compose volume, sandbox workspaces and matching
sandbox containers, service-specific `services/hermes/.env` values, its public routes,
and Hermes images when no remaining container uses them. A permission-restricted
backup of `services/hermes/.env` is retained. OpenDock code, shared infrastructure,
global settings, Caddy certificate state, and unrelated files are preserved.
Use `./opendock remove hermes --dry-run` to review the plan without changes.

The default public hostname is `hermes.<STACK_DOMAIN>`. Launching Hermes by
service name creates that default route if it is missing. To use a different
hostname, add it first and launch that hostname:

```sh
./opendock route add agent.example.com hermes
./opendock launch agent.example.com
```

The dashboard username and generated password are stored in the private
`services/hermes/.env` as
`HERMES_DASHBOARD_USERNAME` and `HERMES_DASHBOARD_PASSWORD`.
The username is the value entered during `./opendock setup hermes`; OpenDock
generates the password without printing it. From the repository root, retrieve
it with:

```sh
grep '^HERMES_DASHBOARD_PASSWORD=' services/hermes/.env
```

Treat the output as a secret and do not paste it into logs or chat. This browser
login protects the dashboard; Hermes onboarding separately configures its model
provider and credentials. `./opendock launch hermes` skips that onboarding when
a default model is already configured in Hermes' persistent data volume. To
intentionally open the provider and integration setup again, run
`./opendock service hermes onboard`.

For a public hostname, protect access with Cloudflare Access or another
identity-aware access layer. Hermes' built-in username/password login is for
trusted networks or VPNs and is not intended as the only protection on the
public internet.

## Docker sandbox boundary

Hermes runs command execution in a separate Docker container with its own
filesystem and process namespace. OpenDock mounts the Docker socket into the
Hermes service so Hermes can create and manage that sandbox. This grants the
Hermes runtime control of the Docker engine used by OpenDock. Treat the Hermes
runtime as trusted: anyone who can compromise it can control containers and
volumes managed by that engine. The agent's normal command tools execute in
the sandbox and do not receive the socket mount.

The sandbox persists across commands and gateway restarts. Hermes does not
mount the OpenDock checkout into the sandbox by default. The sandbox has
network access by default so agent tools can reach external services; change
`terminal.docker_network` in Hermes configuration if commands should be
offline.

OpenDock detects the Docker socket group ID and passes it to the Hermes
container so its unprivileged process can access the socket. It also mounts
`services/hermes/data/sandboxes/` at the same absolute path inside Hermes and
on the Docker host. The Docker daemon resolves bind-mount paths on the host,
so this matching path is required for Hermes' persistent sandbox to start.
Set `DOCKER_SOCKET` in the environment before running OpenDock commands if the
Docker socket is at a non-standard path.

## Persistent data and updates

Hermes configuration, credentials, conversations, skills, and memories live in
the `hermes_data` Docker volume. The execution sandbox has its own persistent
workspace managed by Hermes. Removing either volume deletes its data.

Tracked runtime defaults are in `services/hermes/.env.default`; Renovate follows
`HERMES_VERSION` there and proposes new stable tags. Host-specific overrides and
generated credentials go in the ignored `services/hermes/.env`. OpenDock loads
the default first and the local file second, so a local `HERMES_VERSION` override
continues to pin that host until the key is removed. `./opendock info hermes`
shows the effective image and container status.
