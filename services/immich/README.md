# Immich

Immich provides self-hosted photo and video backup with albums, search, and machine-learning powered discovery.

Default public URL:

```text
https://photos.<STACK_DOMAIN>
```

## Configuration

Service defaults live in `services/immich/.env.default`; local values and secrets are stored in `services/immich/.env`.

Generated secrets live in the repository-level `services/immich/.env`:

```env
IMMICH_DB_PASSWORD=change-immich-db-password
```

OpenDock fills this automatically before Immich starts when it is empty or still a placeholder. Existing real values are kept.

Immich uses the shared Redis service from `infra/` and runs its own app-specific PostgreSQL container with the vector extensions required by Immich.

## Storage

Immich stores uploaded photos and videos in:

```text
services/immich/data/library
```

On first launch, OpenDock asks whether to keep this path or use another
location and remembers the choice. To review or change it later, run
`./opendock setup immich` and set `IMMICH_LIBRARY_PATH` to an existing absolute
path. For example, use `/mnt/photos/immich` on Linux or
`/Volumes/Photos/immich` on macOS. OpenDock creates the default local directory
if needed. A custom path must already exist and be accessible or launch stops.
Press Enter to keep the default path.
OpenDock does not check whether the directory is on an external disk. Choose a
dedicated directory rather than the filesystem root; complete removal deletes
the configured directory after confirmation.
Changing this setting does not copy an existing library. Back up the library
and database, then follow Immich's migration guidance before switching an
existing installation to another directory.

Immich stores its PostgreSQL database in:

```text
services/immich/data/postgres
```

Keep both directories backed up. The database directory should stay on local storage; Immich does not recommend network shares for PostgreSQL data.

Machine-learning model files are stored in the Docker named volume `immich_model_cache`.

When using Cloudflare Tunnel, large photo or video uploads may be affected by Cloudflare request size limits. Test mobile backup with real videos before relying on it as the only photo backup path.

## Remove

Preview the removal plan with `./opendock remove immich --dry-run`. Complete
removal asks for explicit confirmation and deletes the Immich containers,
`immich_model_cache`, image, configured public route, service-local settings,
the configured library directory (including an external disk directory, if
configured), and `services/immich/data/postgres/`. The library contains
uploaded photos and videos; the database contains Immich's application state.
Back up anything you need before confirming. Shared infrastructure and the
gateway are preserved.
