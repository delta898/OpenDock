# Jellyfin

Jellyfin provides a self-hosted media server for movies, TV shows, music, and music videos.

Default public URL:

```text
https://media.<STACK_DOMAIN>
```

## Configuration

Service defaults live in `services/jellyfin/.env`.

Jellyfin does not require stack-level secrets for the default setup. Create the initial admin user in the Jellyfin web UI after first launch.

## Storage

Jellyfin stores app configuration and cache in Docker named volumes:

- `jellyfin_config`
- `jellyfin_cache`

Media files are stored in:

```text
services/jellyfin/media
```

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
