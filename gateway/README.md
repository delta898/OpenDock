# Gateway

Caddy reverse proxy for the home server stack.

This stack treats Cloudflare Tunnel as the default public exposure layer. Cloudflare handles public DNS, public HTTPS, and browser HTTP-to-HTTPS redirects. Caddy handles internal service routing from the Tunnel origin to Docker containers.

## Setup

```sh
./opendock up gateway
```

The default WordPress, Nextcloud, Immich, Jellyfin, n8n, Uptime Kuma, and Homepage routes are generated from `STACK_DOMAIN` and the service subdomains when `domains.conf` is absent.
Reference snippets can live next to service route files with the `.caddy.example` suffix.

## Layout

```text
caddy/
├── Caddyfile
└── conf.d/
    ├── www.domain.com.caddy.example
    ├── global.caddy
    ├── homepage.caddy
    ├── immich.caddy
    ├── jellyfin.caddy
    ├── n8n.caddy
    ├── nextcloud.caddy
    ├── uptime-kuma.caddy
    └── wordpress.caddy
```

- `Caddyfile` loads all `conf.d/*.caddy` files.
- Automatic HTTP-to-HTTPS redirects are disabled globally so Cloudflare Tunnel can use `http://localhost:80` as the origin without redirect loops.
- `global.caddy` contains reusable snippets.
- Per-service `conf.d/<service>.caddy` files define proxy behavior for Docker services.
- `conf.d/zz-opendock-routes.caddy` is generated from `domains.conf` and should not be edited.
- `*.caddy.example` files are reference snippets and are not loaded by Caddy.

The per-service Caddy files define reusable proxy snippets. Caddy host blocks
are generated from `domains.conf`; the route examples below illustrate the
resulting host-to-upstream behavior.

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

http://blog.example.com {
    import wordpress_proxy
}

https://blog.example.com {
    import wordpress_proxy
}
```

By default, WordPress is published as:

```text
https://blog.<STACK_DOMAIN>
```

Set the main domain in `config/core.env` and the service hostname in `services/wordpress/.env`:

```sh
# config/core.env
STACK_DOMAIN=example.com

# services/wordpress/.env
WORDPRESS_SUBDOMAIN=blog
```

Hostname bindings are managed centrally in the internal route map; the
WordPress proxy behavior remains in this file. Use
`./opendock route add <hostname> wordpress`, then `./opendock launch <hostname>` to publish
another WordPress hostname.

## Static Sites

Use `./opendock route add <hostname> static` to serve files from the read-only mount
`/srv/static-sites/<hostname>`, backed by `static-sites/<hostname>/` on the
host. Then `./opendock launch <hostname>` applies the route. Caddy serves the files
directly without a separate container or runtime.

## Homepage Route

The repository includes `caddy/conf.d/homepage.caddy` as the active Homepage route:

```caddy
(homepage_proxy) {
    import common_proxy
    import security_headers
    import block_bots

    reverse_proxy homepage:3000
}

http://home.example.com {
    import homepage_proxy
}

https://home.example.com {
    import homepage_proxy
}
```

By default, Homepage is published as:

```text
https://home.<STACK_DOMAIN>
```

Set the main domain in `config/core.env` and the service hostname in `services/homepage/.env`:

```sh
# config/core.env
STACK_DOMAIN=example.com

# services/homepage/.env
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

http://n8n.example.com {
    import n8n_proxy
}

https://n8n.example.com {
    import n8n_proxy
}
```

By default, n8n is published as:

```text
https://n8n.<STACK_DOMAIN>
```

Set the main domain in `config/core.env` and the service hostname in `services/n8n/.env`:

```sh
# config/core.env
STACK_DOMAIN=example.com

# services/n8n/.env
N8N_SUBDOMAIN=n8n
```

n8n uses those values to generate `WEBHOOK_URL` automatically.

## Nextcloud Route

The repository includes `caddy/conf.d/nextcloud.caddy` as the active Nextcloud route.

By default, Nextcloud is published as:

```text
https://cloud.<STACK_DOMAIN>
```

Set the main domain in `config/core.env` and the service hostname in `services/nextcloud/.env`:

```sh
# config/core.env
STACK_DOMAIN=example.com

# services/nextcloud/.env
NEXTCLOUD_SUBDOMAIN=cloud
```

Nextcloud also uses those values for trusted domains and reverse proxy overwrite settings.

## Immich Route

The repository includes `caddy/conf.d/immich.caddy` as the active Immich route.

By default, Immich is published as:

```text
https://photos.<STACK_DOMAIN>
```

Set the main domain in `config/core.env` and the service hostname in `services/immich/.env`:

```sh
# config/core.env
STACK_DOMAIN=example.com

# services/immich/.env
IMMICH_SUBDOMAIN=photos
```

## Jellyfin Route

The repository includes `caddy/conf.d/jellyfin.caddy` as the active Jellyfin route.

By default, Jellyfin is published as:

```text
https://media.<STACK_DOMAIN>
```

Set the main domain in `config/core.env` and the service hostname in `services/jellyfin/.env`:

```sh
# config/core.env
STACK_DOMAIN=example.com

# services/jellyfin/.env
JELLYFIN_SUBDOMAIN=media
```

Use Jellyfin for movies, shows, music, and music videos. Use Immich for photo backup and photo library management.

## Uptime Kuma Route

The repository includes `caddy/conf.d/uptime-kuma.caddy` as the active Uptime Kuma route:

```caddy
(uptime_kuma_proxy) {
    import common_proxy
    import security_headers
    import block_bots

    reverse_proxy uptime-kuma:3001
}

http://uptime.example.com {
    import uptime_kuma_proxy
}

https://uptime.example.com {
    import uptime_kuma_proxy
}
```

By default, Uptime Kuma is published as:

```text
https://uptime.<STACK_DOMAIN>
```

Set the main domain in `config/core.env` and the service hostname in `services/uptime-kuma/.env`:

```sh
# config/core.env
STACK_DOMAIN=example.com

# services/uptime-kuma/.env
UPTIME_KUMA_SUBDOMAIN=uptime
```

## Exposure Model

The primary supported exposure model is:

```text
Browser
  -> Cloudflare DNS and HTTPS
  -> Cloudflare Tunnel
  -> http://localhost:80
  -> Caddy
  -> Docker service
```

The route files include both `http://...` and `https://...` site blocks:

- `http://...` is used by Cloudflare Tunnel origin traffic.
- `https://...` keeps direct HTTPS routing possible for advanced manual setups.

Caddy's automatic HTTP-to-HTTPS redirect is intentionally disabled. If Caddy redirects Tunnel origin traffic from HTTP to HTTPS, Cloudflare Tunnel can enter a redirect loop.

Use `https://<service>.<domain>` for public access. Browser HTTP-to-HTTPS redirection is expected to happen at Cloudflare, not at Caddy.

When changing `config/core.env` or Caddy route files, reload or recreate the gateway container:

```sh
./opendock down gateway
./opendock up gateway
```

For Cloudflare Tunnel, set the tunnel Service URL to:

```text
http://localhost:80
```

Direct port forwarding is not the default supported path for this stack. If you use it anyway, forward port 443 to this server and open `https://<service>.<domain>` directly.

If you do not use Cloudflare Tunnel and expose Caddy directly, remove this block from `caddy/Caddyfile`:

```caddy
{
	auto_https disable_redirects
}
```

Then forward both port 80 and 443 to the server. Caddy will restore its default HTTP-to-HTTPS redirects.

## Image Policy

Caddy uses the official `caddy` image. Its tracked version and port defaults are
in `config/gateway.env.default`; local overrides belong in `config/gateway.env`.
