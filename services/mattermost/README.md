# Mattermost

Mattermost provides self-hosted team chat and collaboration.

Default public URL:

```text
https://chat.<STACK_DOMAIN>
```

## Configuration

Service defaults live in `services/mattermost/.env`.

Generated secrets live in the repository-level `common.env`:

```env
POSTGRES_ADMIN_PASSWORD=change-postgres-admin-password
MATTERMOST_DB_PASSWORD=change-mattermost-db-password
```

Outbound email uses the common SMTP relay values in `common.env`:

```env
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=mailer@example.com
SMTP_PASSWORD=change-smtp-password
SMTP_FROM_ADDRESS=mailer@example.com
```

Use `make setup mail` to fill these values interactively. OpenDock maps them into Mattermost's SMTP environment variables.

## First Launch

Start Mattermost with:

```sh
make launch mattermost
```

The `mattermost-db-init` container creates or updates the Mattermost PostgreSQL database and user in the shared `infra` PostgreSQL service. Mattermost then creates its schema on first start.

Mattermost provides a first-run web setup flow. OpenDock does not create the system admin account automatically. Open the public URL after launch and create the first admin in the Mattermost web UI.

Recommended first-run flow:

```sh
make setup mattermost
make setup mail
make launch mattermost
```

Configure `make setup mail` before inviting users or relying on password reset emails.

## Image Policy

- Mattermost defaults to `release-11`, tracking Mattermost 11.x without jumping to a future major version.
- PostgreSQL client defaults to `17-alpine`.
- Versions live in `.env`, not `compose.yml`.
- Avoid `latest` tags.

## Storage

Mattermost stores local app data in Docker named volumes:

- `mattermost_config`
- `mattermost_data`
- `mattermost_logs`
- `mattermost_plugins`
- `mattermost_client_plugins`
- `mattermost_bleve_indexes`

Mattermost stores PostgreSQL data in the shared Docker volume `infra_postgres_data`.

Back up the Mattermost volumes and PostgreSQL volume together.
