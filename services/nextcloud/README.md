# Nextcloud

Nextcloud provides private file sync, sharing, calendars, contacts, and related collaboration features.

Default public URL:

```text
https://cloud.<STACK_DOMAIN>
```

## Configuration

Service defaults live in `services/nextcloud/.env`.

Generated secrets live in the repository-level `common.env`:

```env
NEXTCLOUD_DB_PASSWORD=change-nextcloud-db-password
NEXTCLOUD_ADMIN_PASSWORD=change-nextcloud-admin-password
```

OpenDock fills these automatically before Nextcloud starts when they are empty or still placeholders. Existing real values are kept.

The initial admin account uses:

```env
NEXTCLOUD_ADMIN_USER=admin
```

Changing `NEXTCLOUD_ADMIN_PASSWORD` after the first successful install does not reset the admin password. Use the Nextcloud UI or `occ` for password changes after installation.

## Storage

This stack uses Docker named volumes:

- `nextcloud_html` for the Nextcloud application, config, and installed apps
- `nextcloud_data` for uploaded user files

Named volumes avoid common host filesystem permission problems. For external disks or host bind mounts, adjust the volume section carefully and back up before changing an existing installation.
