# Infra

Shared infrastructure services for the home server stack.

MariaDB root credentials and PostgreSQL administrator credentials are read from the repository-level `config/infra.env`. OpenDock generates them automatically before startup when they are empty or still placeholders.

Recommended image versions are tracked in `config/infra.env.default`; local
overrides belong in `config/infra.env`.

MariaDB and PostgreSQL are shared database services. Application-specific
database objects and adapters are declared by the platform and the installed
service package; do not remove shared database volumes as part of a single
service's cleanup.

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

MariaDB uses its current LTS line as the default. PostgreSQL uses the official
Debian-based image for broad extension and locale compatibility. Redis uses
Alpine as a deliberate exception because it is a compact single-service runtime.
