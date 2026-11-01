# Mattermost

Mattermost provides self-hosted team chat and collaboration.

Default public URL:

```text
https://chat.<STACK_DOMAIN>
```

## Configuration

Service defaults live in `services/mattermost/.env.default`; local values and secrets are stored in `services/mattermost/.env`.

Mattermost's database password lives in `services/mattermost/.env`;
the PostgreSQL administrator password is shared infrastructure config in
`config/infra.env`:

```env
MATTERMOST_DB_PASSWORD=change-mattermost-db-password
```

Outbound email uses the shared SMTP relay values in `config/shared/mail.env`:

```env
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=mailer@example.com
SMTP_PASSWORD=change-smtp-password
SMTP_FROM_ADDRESS=mailer@example.com
```

Use `./opendock setup mail` to fill these values interactively. OpenDock maps them into Mattermost's SMTP environment variables.

## First Launch

Start Mattermost with:

```sh
./opendock launch mattermost
```

The `mattermost-db-init` container creates or updates the Mattermost PostgreSQL database and user in the shared `infra` PostgreSQL service. Mattermost then creates its schema on first start.

Mattermost provides a first-run web setup flow. OpenDock does not create the system admin account automatically. Open the public URL after launch and create the first admin in the Mattermost web UI.

Recommended first-run flow:

```sh
./opendock setup mattermost
./opendock setup mail
./opendock launch mattermost
```

Configure `./opendock setup mail` before inviting users or relying on password reset emails.

## Image Policy

- Mattermost defaults to `release-11`, tracking Mattermost 11.x without jumping to a future major version.
- PostgreSQL client defaults to `17-alpine`.
- Versions live in `.env.default`, not `compose.yml`.
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
