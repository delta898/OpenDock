# DockerPackages

Personal Docker Compose workspace for shared infrastructure, gateway services, and application services.

## Structure

```text
.
├── infra/
│   └── compose.yml
├── gateway/
│   └── caddy/
└── services/
    └── wordpress/
```

## Usage

```sh
make list
make up infra
make up gateway
make up wordpress
make ps infra
make logs infra
make down infra
```

Service compose files follow this convention:

```text
services/<service-name>/compose.yml
```

Then they can be controlled from the project root:

```sh
make up wordpress
make logs wordpress
make down wordpress
```

Gateway route files follow this convention:

```text
gateway/caddy/conf.d/<domain>.caddy
```

Default services committed to this repository should have their active gateway routes in `gateway/caddy/conf.d/`. Reference-only snippets use the `.caddy.example` suffix.

## First Run On Ubuntu Server

If you installed a headless Ubuntu Server, check its internal IP:

```sh
hostname -I
```

Then edit `gateway/.env`:

```sh
WORDPRESS_DOMAIN=<your-server-internal-ip>
```

Example:

```sh
WORDPRESS_DOMAIN=192.168.0.22
```

Start the stack:

```sh
make up infra
make up wordpress
make up gateway
```

Then open WordPress from another device on the same network:

```text
http://<your-server-internal-ip>
```

Later, when you connect a real domain, replace the internal IP with that domain:

```sh
WORDPRESS_DOMAIN=blog.example.com
```

If you use Cloudflare Tunnel, route the public hostname to:

```text
http://localhost:80
```

If you use direct port forwarding instead, forward both ports 80 and 443 to the server. The same WordPress Caddy route supports both Cloudflare Tunnel HTTP origin traffic and direct HTTPS traffic.

After changing `gateway/.env`, recreate the gateway container:

```sh
make down gateway
make up gateway
```

## Sync To Test Machine

Copy the example sync config and edit it locally:

```sh
cp .sync.env.example .sync.env
```

Then set your test machine connection:

```sh
SYNC_TEST_REMOTE=user@test-host
SYNC_TEST_PATH=/home/user/DockerPackages
```

Preview the rsync changes first:

```sh
make sync-dry-run test
```

Then sync:

```sh
make sync test
```

The real `.sync.env` file is intentionally ignored by Git. Sync excludes local runtime data such as `services/*/data/`, including the WordPress webroot.

## Environment

Copy the common env file before running services:

```sh
cp common.env.example common.env
```

Then edit `common.env` locally. It contains shared or sensitive values and is intentionally ignored by Git.

- `common.env` contains shared or sensitive values.
- Each directory `.env` is committed with non-sensitive defaults for that compose project.
