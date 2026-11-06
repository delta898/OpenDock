# Homepage

Default Homepage dashboard service for the home server stack.

This service uses gethomepage's official Docker image and keeps dashboard configuration in `services/homepage/config/`.

## Setup

Set the main stack domain in `config/core.env` and the service hostname in `services/homepage/.env`:

```sh
# config/core.env
STACK_DOMAIN=example.com

# services/homepage/.env
HOMEPAGE_SUBDOMAIN=home
```

The default public URL becomes:

```text
https://home.example.com/
```

Then start the stack:

```sh
./opendock up homepage
./opendock up gateway
```

## Image Policy

- Homepage defaults to `v1.13.2`.
- Versions live in `.env.default`, not `compose.yml`.
- Avoid `latest` tags.

## Config

Homepage is configured with YAML files under:

```text
services/homepage/config/
```

The default dashboard links to the included OpenDock services using the shared `STACK_DOMAIN` and service subdomain settings.

## Remove

Preview the complete removal plan with:

```sh
./opendock remove homepage --dry-run
```

`./opendock remove homepage` asks for explicit confirmation, then removes the
Homepage container, image, configured public route, and service-local
settings. It preserves `services/homepage/config/` because those dashboard YAML
files are tracked source, not generated runtime data. Shared infrastructure
and the gateway are preserved.
