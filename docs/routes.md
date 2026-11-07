# Hostname Routes

OpenDock maps public hostnames to content or an upstream. All managed routes use
the same lifecycle: add the mapping, then launch the hostname to render Caddy
configuration and publish the route through Cloudflare Tunnel.

## Add a route

```text
./opendock route add <type> <hostname> [<target>]
```

The route type comes first, followed by the public hostname. The target is
required for `service` and `external`, and omitted for `static`:

```sh
./opendock route add static docs.example.org
./opendock route add service app.example.org n8n-v3
./opendock route add external ai.example.org http://host.docker.internal:1234
```

Then apply and publish the route:

```sh
./opendock launch docs.example.org
```

### `static`

OpenDock creates `static-sites/<hostname>/` and configures Caddy to serve files
from that directory. Add an `index.html` or other site assets there. OpenDock
does not generate or upload the site content.

```sh
./opendock route add static docs.example.org
./opendock launch docs.example.org
```

### `service`

The target is an installed OpenDock service ID that declares public routing.
This maps an additional hostname to that service; launching the hostname starts
the service and applies its route.

```sh
./opendock route add service app.example.org n8n-v3
./opendock launch app.example.org
```

The service's default hostname remains available. Use a hostname when one
service has multiple routes and you want to select a specific one.

### `external`

The target is an upstream **origin URL** reachable from inside the Caddy
container. Only `http://` and `https://` URLs with a hostname or IP and optional
port are accepted. Do not include credentials, a path, query string, or
fragment; configure path rewrites or access controls at the upstream or in a
separate Caddy configuration.

```sh
./opendock route add external ai.example.org http://host.docker.internal:1234
./opendock launch ai.example.org
```

For LM Studio on a Mac using the default API port, `host.docker.internal` lets
the Caddy container reach the host. On Linux, use a host address or DNS name
that is reachable from the Caddy container. `localhost` refers to the Caddy
container itself, not the machine running Docker.

An external route does not install, start, or secure the upstream application.
Launching it starts or reloads the OpenDock gateway and publishes the hostname;
it does not start the external service. Ensure that the upstream is intended to
be reachable from the public Internet. OpenDock does not add authentication to
external routes. HTTPS upstreams must present a certificate trusted by Caddy.

## Inspect and remove routes

```sh
./opendock route show
./opendock route show ai.example.org
./opendock route remove ai.example.org
```

The route list shows each hostname, type, and target. Removing a route removes
its OpenDock mapping and managed Cloudflare Tunnel/DNS entries when Cloudflare
is configured. It does not stop an external upstream or delete static site
files.

Routes are stored in the private host-local `domains.conf` file. Its format
uses the same order as the CLI:

```text
static docs.example.org
service app.example.org n8n-v3
external ai.example.org http://host.docker.internal:1234
```

The file is written with restrictive permissions. External URLs must not
contain secrets because route targets are also shown by `route show` and
written in generated Caddy configuration.

## Default service routes

When no explicit `domains.conf` exists, OpenDock derives routes for installed
services from the primary domain and each service's descriptor routing
metadata. For example, a service whose subdomain setting resolves to `app`
under `example.org` gets `app.example.org`. Explicit `domains.conf` entries
provide additional or customized routes.

Public routes require Cloudflare setup and a Tunnel connector that can reach
the OpenDock Caddy gateway. Configure it with:

```sh
./opendock setup cloudflare
```
