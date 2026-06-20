# Gateway

Caddy reverse proxy for the home server stack.

## Setup

```sh
make up gateway
```

The default WordPress route is active under `caddy/conf.d/wordpress.caddy`.
Reference snippets can live next to real route files with the `.caddy.example` suffix.

## Layout

```text
caddy/
├── Caddyfile
└── conf.d/
    ├── www.domain.com.caddy.example
    ├── global.caddy
    └── wordpress.caddy
```

- `Caddyfile` loads all `conf.d/*.caddy` files.
- `global.caddy` contains reusable snippets.
- `conf.d/wordpress.caddy` is the default WordPress route.
- `*.caddy.example` files are reference snippets and are not loaded by Caddy.
- Additional site-specific reverse proxy files can be added as `conf.d/<domain>.caddy`.

## WordPress Route

The repository includes `caddy/conf.d/wordpress.caddy` as the active WordPress route:

```caddy
{$WORDPRESS_DOMAIN:localhost} {
    import common_proxy
    import security_headers
    import block_bots

    @blocked_wordpress_paths {
        path /xmlrpc.php /wp-config.php /readme.html /license.txt
    }
    respond @blocked_wordpress_paths "" 404

    reverse_proxy {$WORDPRESS_UPSTREAM:wordpress:80}
}
```

Edit `gateway/.env`:

```sh
WORDPRESS_DOMAIN=blog.example.com
WORDPRESS_UPSTREAM=wordpress:80
```

The upstream container must be connected to `shared-net`.

The default domain is `localhost`, so the stack can be tested on the same machine after cloning:

```text
http://localhost
```

Set `WORDPRESS_DOMAIN` to a real domain you control before exposing the server publicly.

For LAN-only testing from another machine, temporarily set:

```sh
WORDPRESS_DOMAIN=:80
```

## Image Policy

Caddy uses the official `caddy` image. The default version is kept in `.env` and referenced from `compose.yml` so users can change versions without editing Compose structure.
