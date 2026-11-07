# Gateway

OpenDock uses Caddy as the shared reverse proxy. Cloudflare Tunnel is the
default public entrypoint: Cloudflare handles public DNS and TLS, while Caddy
routes the Tunnel's HTTP origin to the selected upstream.

Start the gateway with:

```sh
./opendock up gateway
```

OpenDock generates hostname routes from its route map. Installed service
packages contribute optional Caddy handlers; external routes point to an
upstream reachable from the Caddy container, and static routes serve files
from `static-sites/<hostname>/`.

## Caddy files

```text
gateway/caddy/
├── Caddyfile
└── conf.d/
    ├── global.caddy
    ├── www.domain.com.caddy.example
    ├── yy-opendock-service-handlers.caddy  # generated
    └── zz-opendock-routes.caddy            # generated
```

The `Caddyfile` loads `conf.d/*.caddy`. `global.caddy` contains shared
snippets. The `yy-` handler imports and `zz-` route map are generated; do not
edit them. Files ending in `.caddy.example` are reference examples and are not
loaded by Caddy.

Automatic HTTP-to-HTTPS redirects are disabled because Cloudflare Tunnel
terminates public TLS and forwards HTTP to the configured Caddy origin, which
defaults to `http://localhost:80`. Direct public Caddy exposure is not the
supported default.

See [`../docs/routes.md`](../docs/routes.md) for route types and commands.
