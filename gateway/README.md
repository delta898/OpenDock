# Gateway

Caddy reverse proxy for the home server stack.

## Setup

```sh
make up gateway
```

The default WordPress, n8n, Uptime Kuma, and Homepage routes are active under `caddy/conf.d/`.
Reference snippets can live next to real route files with the `.caddy.example` suffix.

## Layout

```text
caddy/
├── Caddyfile
└── conf.d/
    ├── www.domain.com.caddy.example
    ├── global.caddy
    ├── homepage.caddy
    ├── n8n.caddy
    ├── uptime-kuma.caddy
    └── wordpress.caddy
```

- `Caddyfile` loads all `conf.d/*.caddy` files.
- `global.caddy` contains reusable snippets.
- `conf.d/homepage.caddy` is the default Homepage route.
- `conf.d/wordpress.caddy` is the default WordPress route.
- `conf.d/n8n.caddy` is the default n8n route.
- `conf.d/uptime-kuma.caddy` is the default Uptime Kuma route.
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

http://{$WORDPRESS_SUBDOMAIN:blog}.{$STACK_DOMAIN:localhost} {
    import wordpress_proxy
}

https://{$WORDPRESS_SUBDOMAIN:blog}.{$STACK_DOMAIN:localhost} {
    import wordpress_proxy
}
```

By default, WordPress is published as:

```text
https://blog.<STACK_DOMAIN>
```

Set the domain and subdomain in `common.env`:

```sh
STACK_DOMAIN=example.com
WORDPRESS_SUBDOMAIN=blog
```

The upstream container must be connected to `shared-net`.

## Homepage Route

The repository includes `caddy/conf.d/homepage.caddy` as the active Homepage route:

```caddy
(homepage_proxy) {
    import common_proxy
    import security_headers
    import block_bots

    reverse_proxy homepage:3000
}

http://{$HOMEPAGE_SUBDOMAIN:home}.{$STACK_DOMAIN:localhost} {
    import homepage_proxy
}

https://{$HOMEPAGE_SUBDOMAIN:home}.{$STACK_DOMAIN:localhost} {
    import homepage_proxy
}
```

By default, Homepage is published as:

```text
https://home.<STACK_DOMAIN>
```

Set the domain and subdomain in `common.env`:

```sh
STACK_DOMAIN=example.com
HOMEPAGE_SUBDOMAIN=home
```

## n8n Route

The repository includes `caddy/conf.d/n8n.caddy` as the active n8n route:

```caddy
(n8n_proxy) {
    import common_proxy
    import security_headers
    import block_bots

    reverse_proxy n8n:5678
}

http://{$N8N_SUBDOMAIN:n8n}.{$STACK_DOMAIN:localhost} {
    import n8n_proxy
}

https://{$N8N_SUBDOMAIN:n8n}.{$STACK_DOMAIN:localhost} {
    import n8n_proxy
}
```

By default, n8n is published as:

```text
https://n8n.<STACK_DOMAIN>
```

Set the domain and subdomain in `common.env`:

```sh
STACK_DOMAIN=example.com
N8N_SUBDOMAIN=n8n
```

n8n uses those values to generate `WEBHOOK_URL` automatically.

## Uptime Kuma Route

The repository includes `caddy/conf.d/uptime-kuma.caddy` as the active Uptime Kuma route:

```caddy
(uptime_kuma_proxy) {
    import common_proxy
    import security_headers
    import block_bots

    reverse_proxy uptime-kuma:3001
}

http://{$UPTIME_KUMA_SUBDOMAIN:uptime}.{$STACK_DOMAIN:localhost} {
    import uptime_kuma_proxy
}

https://{$UPTIME_KUMA_SUBDOMAIN:uptime}.{$STACK_DOMAIN:localhost} {
    import uptime_kuma_proxy
}
```

By default, Uptime Kuma is published as:

```text
https://uptime.<STACK_DOMAIN>
```

Set the domain and subdomain in `common.env`:

```sh
STACK_DOMAIN=example.com
UPTIME_KUMA_SUBDOMAIN=uptime
```

## Exposure

The routes support both common home-server exposure styles:

- Cloudflare Tunnel forwards to Caddy over HTTP and uses the `http://...` block.
- Direct port forwarding lets Caddy serve HTTPS itself and uses the `https://...` block.

When changing `common.env` or Caddy route files, reload or recreate the gateway container:

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
