# Docmost

Docmost is a self-hosted collaborative wiki and knowledge base with real-time
editing and Spaces. The Community edition is open source under AGPL-3.0. The
official pricing page lists Bases (database and Kanban views) among Business
features, so check the current plan matrix if those Notion-style features are
the main reason for choosing Docmost.

Default public URL:

```text
https://docmost.<STACK_DOMAIN>
```

## Launch

```sh
./opendock launch docmost
```

OpenDock prepares its database in the shared PostgreSQL service, then starts
Docmost. Uploaded files are stored in the `docmost_storage` Compose volume.
The first visit opens Docmost's workspace and owner setup. Use the owner setup
to create the first account; invite other users from Docmost after that.

The service uses the shared Redis service with database index 1 and the shared
SMTP settings for invitation and account email. SMTP is optional for starting
Docmost, but invitations and email-dependent account flows need a working
relay. Configure it with `./opendock setup mail`; choose `SMTP_SECURE=true` for
implicit TLS on port 465.

## Configuration and data

Defaults and image versions are tracked in `.env.default`; machine-specific
values and generated secrets are stored in the ignored `.env` file. Use
`./opendock setup docmost` to review its settings. OpenDock generates the
PostgreSQL password and application secret when they are missing.

PostgreSQL data lives in the shared infra volume. Docmost owns only the
`docmost` database and database role there. Uploaded files live in the
`docmost_storage` named volume. Back up both the shared PostgreSQL data and
Docmost's upload volume.

## Remove

Preview with `./opendock remove docmost --dry-run`. Confirmed removal deletes
Docmost's containers, image, upload volume, configured public route, and
service-local settings. It removes only Docmost's database and role from the
shared PostgreSQL service; other services and shared infrastructure remain.
