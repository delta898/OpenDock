# Configuration

OpenDock keeps tracked defaults separate from private, host-specific values.
Tracked defaults use the `.env.default` suffix and are committed. Effective
`.env` files contain local overrides and secrets and are ignored by Git.

## Configuration owners

| Owner | Tracked defaults | Private effective values |
| --- | --- | --- |
| Core | `config/core.env.default` | `config/core.env` |
| Shared infrastructure | `config/infra.env.default` | `config/infra.env` |
| Gateway | `config/gateway.env.default` | `config/gateway.env` |
| Shared concern | `config/shared/<concern>.env.default` | `config/shared/<concern>.env` |
| Cloudflare | `config/cloudflare.env.default` | `config/cloudflare.env` |
| Installed service | Active package release's `.env.default` | `config/extensions/<service-id>.env` |

TOML descriptors declare setting ownership and setup behavior. Core,
infrastructure, and gateway metadata lives beside each component. Shared
concerns keep metadata and defaults together under `config/shared/`. Installed
service metadata and runtime defaults come from the active package release.

Cloudflare values are kept together in `config/cloudflare.env`. OpenDock uses
`CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_TUNNEL_ID` to publish routes and DNS;
the `cloudflared` connector uses `CLOUDFLARED_TUNNEL_TOKEN`. Bootstrap accepts
the connector token and stores it in that same private file. All three values
are excluded from Git and remote sync.

## Value precedence

Compose interpolation reads the tracked defaults first, then the matching
private effective files, with the process environment taking final precedence.
OpenDock passes these files explicitly; Compose `env_file:` serves a different
purpose and does not replace interpolation files.

For an installed service, the package's `.env.default` is paired with its
private `config/extensions/<service-id>.env` override. Updating a package
therefore refreshes defaults without overwriting host-specific choices. Remove
a private override to use the current default again.

Use `./opendock setup [service-id]` to review settings and repair generated
values. OpenDock keeps existing real values and creates restrictive backups
before rewriting private configuration. `launch` also creates missing
machine-owned secrets automatically before validation.

## Older installations

OpenDock may encounter older private configuration during an upgrade. It
migrates registered values to their current owners and keeps restrictive
backups. If a legacy file contains an unknown setting, migration stops before
changing that file so the value can be reviewed safely. Historical service
paths are migration inputs only; new service packages are installed from the
catalog and store private settings under `config/extensions/`.

Never add machine credentials or host-specific values to a tracked defaults
file.
