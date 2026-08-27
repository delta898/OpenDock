# Supabase

OpenDock runs a complete single-project Supabase stack behind Caddy and Kong.
No Supabase-specific setup is required before the first launch:

```sh
make launch supabase
```

The command starts the shared network prerequisite, generates all database,
JWT, Studio, Realtime, and metadata secrets, initializes the dedicated
PostgreSQL database, starts the containers in health order, reloads Caddy, and
publishes the route when Cloudflare sync is configured.

An idempotent database bootstrap runs after PostgreSQL becomes healthy. It
repairs required API schemas on an existing compatible database as well as on
a fresh installation, so users do not need to run SQL manually after updates.
After the stack becomes healthy, OpenDock automatically smoke-tests the
containers, database contract, Auth, REST, GraphQL, Storage, Realtime, Studio,
and the included Edge Function. A failed check makes `make launch supabase`
fail with the affected component instead of reporting a partial deployment as
ready.

Default URL:

```text
https://supabase.<STACK_DOMAIN>
```

## Included components

- PostgreSQL with Supabase extensions and role initialization
- Auth (GoTrue)
- PostgREST
- Realtime
- Storage and imgproxy
- postgres-meta and Studio
- Edge Runtime with a `hello` smoke-test function
- Kong API gateway
- Inbucket as the local SMTP fallback

Persistent data stays under `services/supabase/data/` and is ignored by Git.

## Studio login

Studio is protected by HTTP Basic Auth at the root URL. Credentials are
generated into the repository-level `common.env`:

```env
SUPABASE_DASHBOARD_USER=opendock
SUPABASE_DASHBOARD_PASSWORD=<generated>
```

API endpoints use the generated anon or service-role key:

```text
/auth/v1/
/rest/v1/
/graphql/v1
/realtime/v1/
/storage/v1/
/functions/v1/
```

The service-role key bypasses row-level security. Never expose it to browsers
or commit `common.env`.

## Email behavior

Email accounts are auto-confirmed by default so a fresh zero-config deployment
is immediately usable. To require email confirmation, set
`SUPABASE_EMAIL_AUTOCONFIRM=false` in `services/supabase/.env`, configure the
shared SMTP relay with `make setup mail`, and recreate the Auth container.

## Edge Functions

Functions live at `services/supabase/config/functions/<name>/index.ts`.
The included function can be tested with:

```sh
set -a
. ./common.env
set +a
curl "https://${SUPABASE_SUBDOMAIN}.${STACK_DOMAIN}/functions/v1/hello" \
  -H "Authorization: Bearer ${SUPABASE_ANON_KEY}"
```

Restart Supabase after adding a function:

```sh
make restart supabase
```

## Backups

Back up both persistent directories together:

```text
services/supabase/data/db
services/supabase/data/storage
```

A file copy of a running PostgreSQL data directory is not a consistent database
backup. Use `pg_dump` for logical backups or stop Supabase before copying it.

## Upgrading an older local installation

The current stack uses PostgreSQL 17. A data directory created by PostgreSQL 15
cannot be opened directly by PostgreSQL 17. A clean clone is unaffected because
OpenDock creates a new PostgreSQL 17 directory on first launch.

If the old local data is disposable, archive it and let OpenDock initialize a
new database:

```sh
make stop supabase
mkdir -p services/supabase/backups
mv services/supabase/data/db \
  "services/supabase/backups/db-pg15-$(date +%Y%m%d-%H%M%S)"
make launch supabase
```

The move is recoverable and does not delete the PostgreSQL 15 files. If the old
database must be preserved, export it with the matching PostgreSQL 15 server
and restore the logical dump into PostgreSQL 17 instead of using this reset.
