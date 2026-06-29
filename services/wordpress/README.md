# WordPress

Default WordPress service for the home server stack.

This template uses the official WordPress Apache image behind the shared Caddy gateway. It is intentionally simple for first-time users: Caddy proxies HTTP traffic to the WordPress container, and a one-shot MariaDB client container creates the WordPress database and user.

## Setup

Edit `services/wordpress/.env`:

```sh
WORDPRESS_DB_NAME=wordpress
WORDPRESS_DB_USER=wordpress
```

Edit `common.env`:

```sh
STACK_DOMAIN=example.com
WORDPRESS_SUBDOMAIN=blog
```

`MARIADB_ROOT_PASSWORD` and `WORDPRESS_DB_PASSWORD` are generated automatically before WordPress starts. Existing real values in `common.env` are kept.

The matching Caddy route lives in `gateway/caddy/conf.d/wordpress.caddy`.
By default, WordPress is published as:

```text
https://blog.example.com/
```

The default WordPress upstream is `wordpress:80`, matching the `WORDPRESS_CONTAINER_NAME` value in `services/wordpress/.env`.

Then start the stack:

```sh
make up infra
make up wordpress
make up gateway
```

## HTTPS Behind Caddy

OpenDock publishes WordPress as `https://blog.<STACK_DOMAIN>` through Cloudflare Tunnel and Caddy, while the WordPress Apache container receives internal HTTP traffic. The Caddy route forwards HTTPS proxy headers, and the WordPress container config turns those headers into `$_SERVER['HTTPS'] = 'on'` for new installs. This lets WordPress enable HTTPS-only features such as Application Passwords.

## Multisite

OpenDock can convert the WordPress site to subdirectory multisite mode:

```sh
make wp-multisite
```

The command uses `STACK_DOMAIN` and `WORDPRESS_SUBDOMAIN` to configure the network host. With the default subdomain, the network uses URLs like:

```text
https://blog.example.com/site-name/
```

The command prints a warning and asks for confirmation before making changes. WordPress multisite changes configuration and database behavior; returning to single-site mode later is a migration task, not a simple toggle after you create sites or content.

For existing installs, the command also patches `wp-config.php` with OpenDock's reverse proxy HTTPS detection block.

Before converting, OpenDock creates backups:

```text
services/wordpress/backups/wp-config.php.<timestamp>
services/wordpress/backups/.htaccess.<timestamp>
services/wordpress/backups/wordpress-multisite-<timestamp>.sql
```

For non-interactive automation:

```sh
make wp-multisite YES=1
```

## Image Policy

- WordPress defaults to `7-php8.3-apache`.
- WordPress CLI defaults to `wordpress:cli-php8.3`.
- MariaDB client defaults to `11.8-noble`, matching the infra recommendation.
- Versions live in `.env`, not `compose.yml`.
- Avoid `latest` tags.

## Webroot

WordPress files are stored on the host at:

```text
services/wordpress/data/webroot/
```

This path is intentionally ignored by Git. It is useful for search engine ownership files, manual inspection, and file-level backup or rsync workflows.

## Notes

The `wordpress-db-init` service is safe to run repeatedly. It uses `CREATE DATABASE IF NOT EXISTS` and `CREATE USER IF NOT EXISTS`.

Generated password values are stored in `common.env`. The `wordpress-db-init` service keeps existing database users and updates only when the generated values are still placeholders before startup.
