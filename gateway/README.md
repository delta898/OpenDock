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
(wordpress_proxy) {
    import common_proxy
    import security_headers
    import block_bots

    @blocked_wordpress_paths {
        path /xmlrpc.php /wp-config.php /readme.html /license.txt
    }
    respond @blocked_wordpress_paths "" 404

    reverse_proxy wordpress:80
}

http://localhost {
    import wordpress_proxy
}

https://localhost {
    import wordpress_proxy
}
```

Edit `gateway/caddy/conf.d/wordpress.caddy` and replace `localhost` with your server IP or domain:

```caddy
http://blog.example.com {
    import wordpress_proxy
}

https://blog.example.com {
    import wordpress_proxy
}
```

The upstream container must be connected to `shared-net`.

The route supports both common home-server exposure styles:

- Cloudflare Tunnel forwards to Caddy over HTTP and uses the `http://...` block.
- Direct port forwarding lets Caddy serve HTTPS itself and uses the `https://...` block.

The default domain is `localhost`, so the stack can be tested on the same machine after cloning:

```text
http://localhost
```

For a headless Ubuntu Server, replace `localhost` with the server's internal IP first:

```sh
hostname -I
```

Example:

```caddy
http://192.168.0.22 {
    import wordpress_proxy
}

https://192.168.0.22 {
    import wordpress_proxy
}
```

Then open `http://192.168.0.22` from another device on the same network.

Set the route domain to a real domain you control before exposing the server publicly.

When changing Caddy route files, reload or recreate the gateway container:

```sh
make down gateway
make up gateway
```

For Cloudflare Tunnel, set the tunnel Service URL to:

```text
http://localhost:80
```

For direct port forwarding, forward both ports 80 and 443 to this server.

## Image Policy

Caddy uses the official `caddy` image. The default version is kept in `.env` and referenced from `compose.yml` so users can change versions without editing Compose structure.
