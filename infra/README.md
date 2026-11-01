# Infra

Shared infrastructure services for the home server stack.

MariaDB root credentials and PostgreSQL administrator credentials are read from the repository-level `config/infra.env`. OpenDock generates them automatically before startup when they are empty or still placeholders.

Recommended image versions are tracked in `config/infra.env.default`; local
overrides belong in `config/infra.env`.

MariaDB runs with `READ-COMMITTED` transaction isolation for Nextcloud compatibility.

PostgreSQL is available as the shared relational database for services that do not need app-specific PostgreSQL extensions.

## Image Policy

- Prefer Ubuntu Noble based images by default.
- Use Alpine only when the service has no known C runtime or compatibility issues in this stack, and the size/security benefit is meaningful.
- Keep image versions in `config/infra.env.default` instead of hardcoding them in `compose.yml`.
- Commit non-sensitive recommended defaults in `config/infra.env.default`.
- Avoid `latest` tags.

## Recommended Defaults

```sh
MARIADB_VERSION=11.8-noble
POSTGRES_VERSION=18-bookworm
REDIS_VERSION=8-alpine
```

MariaDB uses the current LTS line as the default. PostgreSQL uses the official Debian-based image for broad extension and locale compatibility. Redis uses Alpine as a deliberate exception because it is a compact single-service runtime with a strong image size benefit and low compatibility risk for this stack.
