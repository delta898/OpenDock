# Hermes Agent

Hermes Agent runs as an OpenDock service with its web dashboard routed through
Caddy. Agent terminal, code execution, and file tools use Hermes' Docker
backend, which runs commands in a separate, persistent sandbox container.

## Setup

Configure the domain and dashboard login values:

```sh
./opendock setup hermes
```

Run Hermes' interactive onboarding once to select a model provider and optional
messaging integrations. Start OpenDock's shared network first:

```sh
./opendock up infra
./opendock service hermes onboard
```

Then launch the dashboard hostname (default `hermes.<STACK_DOMAIN>`):

```sh
./opendock launch hermes.example.com
```

The dashboard username and generated password are stored in `common.env` as
`HERMES_DASHBOARD_USERNAME` and `HERMES_DASHBOARD_PASSWORD`.

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

The image is pinned in `common.env` as `HERMES_VERSION`; Renovate can propose
new stable tags. `./opendock info hermes` shows the configured image and
container status.
