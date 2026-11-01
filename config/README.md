# Configuration files

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

Core owns settings such as `STACK_DOMAIN`. Infra owns shared database
administrator credentials. Shared files are for values deliberately consumed
by several services, such as SMTP relay settings and the MariaDB client image
used by WordPress and Nextcloud bootstrap containers.

## Service configuration

Every service uses the same service-owned layout:

```text
services/<service>/.env.default   # tracked defaults and Renovate image versions
services/<service>/.env           # local overrides and secrets; ignored by Git
```

Service hostnames, image versions, runtime defaults, and service-specific
secrets belong to that service. Core, shared infrastructure, shared concerns,
and external Cloudflare credentials remain in their own files.

## Effective value order

OpenDock passes Compose interpolation files explicitly; `env_file:` inside a
Compose file serves a different purpose. For each service the order is:

```text
config/core.env.default     -> config/core.env
config/infra.env.default    -> config/infra.env
config/gateway.env.default -> config/gateway.env
config/shared/mail.env.default -> config/shared/mail.env
config/shared/database.env.default -> config/shared/database.env
services/<service>/.env.default -> services/<service>/.env
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
On the first initialization after migration, values left in `services/*/.env`
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
