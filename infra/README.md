# Infra

Shared infrastructure services for the home server stack.

MariaDB root credentials are read from the repository-level `common.env`.

MariaDB runs with `READ-COMMITTED` transaction isolation for Nextcloud compatibility.

## Image Policy

- Prefer Ubuntu Noble based images by default.
- Use Alpine only when the service has no known C runtime or compatibility issues in this stack, and the size/security benefit is meaningful.
- Keep image versions in `.env` instead of hardcoding them in `compose.yml`.
- Commit non-sensitive recommended defaults in `.env`.
- Avoid `latest` tags.

## Recommended Defaults

```sh
MARIADB_VERSION=11.8-noble
REDIS_VERSION=8-alpine
```

MariaDB uses the current LTS line as the default. Redis uses Alpine as a deliberate exception because it is a compact single-service runtime with a strong image size benefit and low compatibility risk for this stack.
