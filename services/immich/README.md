# Immich

Immich provides self-hosted photo and video backup with albums, search, and machine-learning powered discovery.

Default public URL:

```text
https://photos.<STACK_DOMAIN>
```

## Configuration

Service defaults live in `services/immich/.env`.

Required secrets live in the repository-level `common.env`:

```env
IMMICH_DB_PASSWORD=change-immich-db-password
```

Immich uses the shared Redis service from `infra/` and runs its own app-specific PostgreSQL container with the vector extensions required by Immich.

## Storage

Immich stores uploaded photos and videos in:

```text
services/immich/data/library
```

Immich stores its PostgreSQL database in:

```text
services/immich/data/postgres
```

Keep both directories backed up. The database directory should stay on local storage; Immich does not recommend network shares for PostgreSQL data.

Machine-learning model files are stored in the Docker named volume `immich_model_cache`.

When using Cloudflare Tunnel, large photo or video uploads may be affected by Cloudflare request size limits. Test mobile backup with real videos before relying on it as the only photo backup path.
