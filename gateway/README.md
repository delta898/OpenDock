# Gateway

Caddy reverse proxy for the home server stack.

This stack treats Cloudflare Tunnel as the default public exposure layer. Cloudflare handles public DNS, public HTTPS, and browser HTTP-to-HTTPS redirects. Caddy handles internal HTTP service routing from the Tunnel origin to Docker containers. OpenDock generates HTTP-only Caddy sites in this mode, so Caddy does not request a second certificate from Let's Encrypt.

## Setup

```sh
./opendock up gateway
```

Routes are generated from `domains.conf`. Installed service packages provide
their Caddy handlers; OpenDock generates a global handler-import file before
the generated hostname routes. Reference snippets can live next to service
route files with the `.caddy.example` suffix.

## Layout

```text
caddy/
├── Caddyfile
└── conf.d/
    ├── www.domain.com.caddy.example
    ├── global.caddy
    ├── yy-opendock-service-handlers.caddy  (generated)
    └── zz-opendock-routes.caddy            (generated)
```

- `Caddyfile` loads all `conf.d/*.caddy` files.
- Automatic HTTP-to-HTTPS redirects are disabled globally. OpenDock publishes
  managed Tunnel hostnames to its configured Caddy origin, defaulting to
  `http://localhost:80`.
- `global.caddy` contains reusable snippets.
- `yy-opendock-service-handlers.caddy` imports routing snippets from installed
  package releases at Caddyfile top level. OpenDock generates it; do not edit it.
- `conf.d/zz-opendock-routes.caddy` is generated from `domains.conf` and should not be edited.
- `*.caddy.example` files are reference snippets and are not loaded by Caddy.

Direct public TLS termination at Caddy is not part of the current generated-route
mode. It needs explicit exposure-mode support, port forwarding, and ACME
reachability; removing the `auto_https` option alone is insufficient.

Service package routing files define reusable proxy snippets. Caddy host
blocks are generated from `domains.conf`; the route examples below illustrate
the resulting host-to-upstream behavior.

## Optional Service Routes

The following examples describe handlers supplied by packages in
OpenDock-Services. They are not active in a fresh OpenDock checkout. Install
the corresponding package before using its route or service ID.

### WordPress Route

The WordPress package provides `routing/wordpress.caddy`:

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
```

By default, WordPress is published as:

```text
https://blog.<STACK_DOMAIN>
```

Set the main domain in `config/core.env` and the service hostname in the package-owned configuration:

```sh
# config/core.env
STACK_DOMAIN=example.com

# config/extensions/wordpress.env
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

### n8n Route

The n8n package provides `routing/n8n.caddy`:

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
```

By default, n8n is published as:

```text
https://n8n.<STACK_DOMAIN>
```

Set the main domain in `config/core.env` and the service hostname in the package-owned configuration:

```sh
# config/core.env
STACK_DOMAIN=example.com

# config/extensions/n8n.env
N8N_SUBDOMAIN=n8n
```

n8n uses those values to generate `WEBHOOK_URL` automatically.

### Nextcloud Route

The Nextcloud package provides `routing/nextcloud.caddy`.

By default, Nextcloud is published as:

```text
https://cloud.<STACK_DOMAIN>
```

Set the main domain in `config/core.env` and the service hostname in the package-owned configuration:

```sh
# config/core.env
STACK_DOMAIN=example.com

# config/extensions/nextcloud.env
NEXTCLOUD_SUBDOMAIN=cloud
```

Nextcloud also uses those values for trusted domains and reverse proxy overwrite settings.

### Immich Route

The Immich package provides `routing/immich.caddy`.

By default, Immich is published as:

```text
https://photos.<STACK_DOMAIN>
```

Set the main domain in `config/core.env` and the service hostname in the package-owned configuration:

```sh
# config/core.env
STACK_DOMAIN=example.com

# config/extensions/immich.env
IMMICH_SUBDOMAIN=photos
```

### Jellyfin Route

The Jellyfin package provides `routing/jellyfin.caddy`.

By default, Jellyfin is published as:

```text
https://media.<STACK_DOMAIN>
```

Set the main domain in `config/core.env` and the service hostname in the package-owned configuration:

```sh
# config/core.env
STACK_DOMAIN=example.com

# config/extensions/jellyfin.env
JELLYFIN_SUBDOMAIN=media
```

Use Jellyfin for movies, shows, music, and music videos. Use Immich for photo backup and photo library management.

## Exposure Model

The primary supported exposure model is:

```text
Browser
  -> Cloudflare DNS and HTTPS
  -> Cloudflare Tunnel
  -> Caddy HTTP origin reachable from the connector
  -> Caddy
  -> Docker service
```

Generated route files use HTTP-only Caddy site blocks. Cloudflare Tunnel
terminates public TLS and forwards HTTP to Caddy. OpenDock publishes managed
Tunnel hostnames to the configured origin, which defaults to
`http://localhost:80`.

Caddy's automatic HTTP-to-HTTPS redirect is intentionally disabled. If Caddy redirects Tunnel origin traffic from HTTP to HTTPS, Cloudflare Tunnel can enter a redirect loop.

Use `https://<service>.<domain>` for public access. Browser HTTP-to-HTTPS redirection is expected to happen at Cloudflare, not at Caddy.

When changing `config/core.env` or Caddy route files, reload or recreate the gateway container:

```sh
./opendock down gateway
./opendock up gateway
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
