# Jellyfin

Jellyfin provides a self-hosted media server for movies, TV shows, music, and music videos.

Default public URL:

```text
https://media.<STACK_DOMAIN>
```

## Configuration

Service defaults live in `services/jellyfin/.env.default`; local values and secrets are stored in `services/jellyfin/.env`.

Jellyfin does not require stack-level secrets for the default setup. Create the initial admin user in the Jellyfin web UI after first launch.

## Storage

Jellyfin stores app configuration and cache in Docker named volumes:

- `jellyfin_config`
- `jellyfin_cache`

By default, media files are stored in:

```text
services/jellyfin/media
```

On first launch, OpenDock asks whether to keep this path or use another
location and remembers the choice. To review or change it later, run
`./opendock setup jellyfin` and set `JELLYFIN_MEDIA_PATH` to an existing
absolute path. For example, use `/mnt/media/jellyfin` on Linux or
`/Volumes/Media/jellyfin` on macOS. OpenDock creates the default local directory
if needed. A custom path must already exist and be accessible or launch stops.
OpenDock does not check whether the directory is on an external disk. Choose a
dedicated directory rather than the filesystem root; complete removal deletes
the configured directory after confirmation.
Press Enter to keep the default path. Configuration and cache remain in Docker
named volumes.

Changing this setting only changes the mounted directory; OpenDock does not
move existing media. For an existing library, stop Jellyfin, copy the media to
the new directory, then update the setting and launch again.

Suggested folders:

```text
services/jellyfin/media/movies
services/jellyfin/media/shows
services/jellyfin/media/music
```

Use Jellyfin primarily for movies, shows, music, and music videos. Use Immich for photo backup and photo library management.

## Notes

Cloudflare Tunnel is useful for the Jellyfin web UI and light remote access. For heavy video streaming, LAN access is usually a better experience.

DLNA discovery and hardware acceleration may require additional host networking or device passthrough settings. They are intentionally not enabled in the default beginner-friendly setup.

## Remove

Preview the removal plan with `./opendock remove jellyfin --dry-run`. Complete
removal asks for explicit confirmation and deletes the Jellyfin containers,
`jellyfin_config` and `jellyfin_cache` volumes, image, configured public route,
service-local settings, and the configured media directory (including an
external disk directory, if configured).
This permanently deletes your media library. The tracked `.gitkeep` directory
placeholders are preserved so removal does not modify repository source.
Shared infrastructure and the gateway are preserved.
