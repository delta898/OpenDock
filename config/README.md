# Configuration files

OpenDock separates tracked defaults from local effective values. Defaults have
the `.env.default` suffix and are committed. The corresponding actual `.env`
files contain host-specific overrides and secrets, are ignored by Git, and are
not Renovate inputs. A few not-yet-migrated services still have tracked legacy
`services/<service>/.env` defaults; those remain Renovate inputs until their
individual migration.

## Platform configuration

| Owner | Tracked defaults | Local effective values |
| --- | --- | --- |
| Core | `config/core.env.default` | `config/core.env` |
| Shared infrastructure | `config/infra.env.default` | `config/infra.env` |
| Shared concern | `config/shared/<concern>.env.default` | `config/shared/<concern>.env` |

Core owns settings such as `STACK_DOMAIN`. Infra owns shared database
administrator credentials. Shared files are for values deliberately consumed
by several services, such as SMTP relay settings.

## Service configuration

Hermes is the pilot for the service-owned layout:

```text
services/hermes/.env.default   # tracked defaults and Renovate image version
services/hermes/.env           # local overrides and secrets; ignored by Git
```

Hermes has no `config/services/hermes.env` file. Its hostname, dashboard
credentials, image version, and container name belong to the Hermes service.
Core domain settings remain in `config/`; Hermes secrets and local choices stay
in the ignored `services/hermes/.env`.

Other services are not migrated yet. They continue to use the current tracked
`services/<service>/.env` runtime defaults together with
`config/services/<service>.env.example` and its private `.env` override, where
present. Their tracked `.env` files remain Renovate inputs during this
transition. Migrate them to `services/<service>/.env.default` and
`services/<service>/.env` individually, only after the Hermes pilot has been
verified.

## Effective value order

OpenDock passes Compose interpolation files explicitly; `env_file:` inside a
Compose file serves a different purpose. For Hermes the order is:

```text
config/core.env.default     -> config/core.env
config/infra.env.default    -> config/infra.env
config/shared/mail.env.default -> config/shared/mail.env
services/hermes/.env.default -> services/hermes/.env
process environment (highest precedence)
```

The default file is loaded first and the matching local file second, so a host
override or secret wins. Setup writes only values the user chooses or secrets
OpenDock generates; unchanged defaults remain live from `.env.default` and
therefore receive Renovate updates. Removing an override restores the default.

For unmigrated services, OpenDock preserves their existing resolution order:
platform defaults and local values, then the selected service's legacy
`config/services/<service>.env.example`, private override, and tracked runtime
`.env`. The ignored local `.env` files for migrated services are never committed
or scanned by Renovate.

Use `./opendock setup [service]` and `./opendock secrets [target]` to manage
values. Changed private files are backed up with restrictive permissions under
`backups/config/`.

## Existing installations

The root `common.env` is a one-time migration input. OpenDock routes known keys
to their owners, keeps the original in `backups/config/`, and removes the old
file after a successful migration. An unknown key stops migration before the
legacy file is changed. For Hermes, migrated `HERMES_*` values go to
`services/hermes/.env`.

Add future defaults to the matching tracked `.env.default` or legacy
`.env.example`, register key ownership in `scripts/opendock_settings.py`, and
never add machine secrets to a tracked defaults file.
