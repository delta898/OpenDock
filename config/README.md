# Configuration files

> This page primarily documents configuration for the legacy in-repository
> service runtime. The new package distribution flow currently supports catalog
> URL settings and package installation; service instance configuration and
> package setup/launch are still being designed and implemented. Do not infer
> that the legacy `services/bundles/` paths are the product model.

OpenDock separates tracked defaults from local effective values. Defaults have
the `.env.default` suffix and are committed. The corresponding actual `.env`
files contain host-specific overrides and secrets, are ignored by Git, and are
not Renovate inputs.

## Platform configuration

| Owner | Tracked defaults | Local effective values |
| --- | --- | --- |
| Core | `config/core.env.default` | `config/core.env` |
| Shared infrastructure | `config/infra.env.default` | `config/infra.env` |
| Gateway | `config/gateway.env.default` | `config/gateway.env` |
| Shared concern | `config/shared/<concern>.env.default` | `config/shared/<concern>.env` |
| Cloudflare integration | `config/cloudflare.env.default` | `config/cloudflare.env` |

`config/cloudflare.env.default` and `config/cloudflare.env` keep all Cloudflare
credentials together: `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_TUNNEL_ID` are
used by OpenDock for route publishing and DNS sync, while
`CLOUDFLARED_TUNNEL_TOKEN` lets the `cloudflared` connector join the
remotely-managed Tunnel. Bootstrap stores the connector token in the private
`config/cloudflare.env`. At runtime it writes a short-lived, permission-
restricted token-only file because `cloudflared --token-file` cannot consume a
dotenv file; the runtime file is removed when the connector exits. The private
`.env` file is ignored by Git and excluded from `./opendock sync`.

Core owns settings such as `STACK_DOMAIN`. Infra owns shared database
administrator credentials. Shared files are for values deliberately consumed
by several services, such as SMTP relay settings and the MariaDB client image
used by WordPress and Nextcloud bootstrap containers. Each shared concern keeps
its descriptor beside its defaults: `config/shared/<concern>.toml` declares
setting ownership and setup prompts, while `.env.default` contains tracked
values. For example, `mail.toml` and `mail.env.default` describe SMTP;
`database.toml` and `database.env.default` describe shared database settings.

## Service configuration

Bundled services keep tracked defaults and local overrides beside their code:

```text
services/bundles/<service>/.env.default   # tracked defaults and Renovate image versions
services/bundles/<service>/.env           # local overrides and secrets; ignored by Git
```

Installed extensions use the package release's `.env.default` and a private
override in `config/extensions/<service>.env`; package updates preserve the
private file. During the split rollout, remaining flat service directories
still use their existing `.env.default` and `.env` paths until migrated.

Service hostnames, image versions, runtime defaults, and service-specific
secrets belong to that service. Core, shared infrastructure, shared concerns,
and Cloudflare credentials remain in their own files under `config/`.

## Effective value order

OpenDock passes Compose interpolation files explicitly; `env_file:` inside a
Compose file serves a different purpose. For each service the order is:

```text
config/core.env.default     -> config/core.env
config/infra.env.default    -> config/infra.env
config/gateway.env.default -> config/gateway.env
config/shared/database.env.default -> config/shared/database.env
config/shared/mail.env.default -> config/shared/mail.env
config/cloudflare.env.default -> config/cloudflare.env
services/bundles/<service>/.env.default -> services/bundles/<service>/.env
extension release/.env.default -> config/extensions/<service>.env
process environment (highest precedence)
```

The default file is loaded first and the matching local file second, so a host
override or secret wins. Setup writes only values the user chooses or secrets
OpenDock generates; unchanged defaults remain live from `.env.default` and
therefore receive Renovate updates. Removing an override restores the default.

Use `./opendock setup [service]` and `./opendock secrets [target]` to manage
values. Changed private files are backed up with restrictive permissions under
`backups/config/`.

## Existing installations

The root `common.env` is a one-time migration input. OpenDock routes known keys
to their owners, keeps the original in `backups/config/`, and removes the old
file after a successful migration. Previous private `config/services/*.env`
overrides are migrated into service-owned `.env` files with restrictive
backups. An unknown key stops migration before the legacy file is changed.
The former tracked `infra/.env` image defaults are moved into
`config/infra.env.default`; non-default local values are preserved in
`config/infra.env`, and the old file receives a restrictive backup before it is
removed.
The former tracked `gateway/.env` Caddy and port defaults are similarly moved
to `config/gateway.env.default`; non-default local values are preserved in
`config/gateway.env` with a restrictive backup.
On the first initialization after migration, values left in service-local `.env`
that match either the new tracked defaults or the previous tracked `.env`
defaults are removed from the private file, so Renovate updates continue to
take effect even when a version changed during migration. Different local
values remain as overrides. Previous service defaults and infra defaults are
recorded in `config/migrations/service-env-v1.json`,
`config/migrations/infra-env-v1.json`, and
`config/migrations/gateway-env-v1.json` for this one-time comparison. Original
files are backed up before they are rewritten or removed.

Add future defaults to the matching tracked `.env.default`, register key
ownership in `scripts/opendock_settings.py`, and never add machine secrets to a
tracked defaults file.
