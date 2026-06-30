# Mastodon

Mastodon provides a self-hosted ActivityPub social networking server.

Default public URL:

```text
https://social.<STACK_DOMAIN>
```

## Configuration

Service defaults live in `services/mastodon/.env`.

Generated secrets live in the repository-level `common.env`:

```env
POSTGRES_ADMIN_PASSWORD=change-postgres-admin-password
MASTODON_DB_PASSWORD=change-mastodon-db-password
MASTODON_SECRET_KEY_BASE=change-mastodon-secret-key-base
MASTODON_OTP_SECRET=change-mastodon-otp-secret
MASTODON_ACTIVE_RECORD_ENCRYPTION_DETERMINISTIC_KEY=change-mastodon-active-record-encryption-deterministic-key
MASTODON_ACTIVE_RECORD_ENCRYPTION_KEY_DERIVATION_SALT=change-mastodon-active-record-encryption-key-derivation-salt
MASTODON_ACTIVE_RECORD_ENCRYPTION_PRIMARY_KEY=change-mastodon-active-record-encryption-primary-key
MASTODON_VAPID_PRIVATE_KEY=change-mastodon-vapid-private-key
MASTODON_VAPID_PUBLIC_KEY=change-mastodon-vapid-public-key
```

The initial owner account is also configured in `common.env`:

```env
MASTODON_ADMIN_USERNAME=opendock
MASTODON_ADMIN_EMAIL=you@example.com
MASTODON_ADMIN_PASSWORD=change-mastodon-admin-password
```

Use `make setup mastodon` to fill these values interactively.

Generate and fill the Mastodon-only secrets manually:

```sh
make secrets mastodon
```

This creates `common.env` from `common.env.example` if needed, then fills missing or placeholder generated values. Existing real values are kept.

`make secrets`, `make up`, `make services`, and `make launch` also fill missing or placeholder generated values before validation when the target needs them. `make check-config` only reports missing values and never changes files.

Mastodon sends account confirmation and notification emails through SMTP. Set the SMTP values in `services/mastodon/.env` or override them locally before opening registrations.

## First Launch

Start the shared infrastructure and Mastodon containers:

```sh
make launch mastodon
```

The `mastodon-db-init` container creates or updates the Mastodon PostgreSQL database and user in the shared `infra` PostgreSQL service. The `mastodon-db-prepare` container then runs Mastodon's database preparation before the web, streaming, and Sidekiq containers start.

On first launch, OpenDock creates `MASTODON_ADMIN_USERNAME` when no owner exists. The generated password printed by Mastodon's internal tooling is ignored, and OpenDock sets the initial login password to `MASTODON_ADMIN_PASSWORD` from `common.env`.

Recommended first-run flow:

```sh
make setup mastodon
make launch mastodon
```

Use a real email address for the owner account. If an owner or `MASTODON_ADMIN_USERNAME` already exists, OpenDock does not change its password automatically. Manage existing account passwords in Mastodon.

## Storage

Mastodon stores uploaded media in:

```text
services/mastodon/data/public/system
```

Mastodon stores PostgreSQL data in the shared Docker volume `infra_postgres_data`.

Back up the media directory and PostgreSQL volume together. If you later enable object storage with `MASTODON_S3_ENABLED=true`, migrate media deliberately before removing local files.
