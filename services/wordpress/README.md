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
MARIADB_ROOT_PASSWORD=change-root-password
WORDPRESS_DB_PASSWORD=change-wordpress-db-password
```

Use different values for `MARIADB_ROOT_PASSWORD` and `WORDPRESS_DB_PASSWORD`. The root password can administer the whole MariaDB server, while the WordPress password is only for the WordPress database user.

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

## Image Policy

- WordPress defaults to `7-php8.3-apache`.
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

The default password values are placeholders. Change them before using this on a public server.
