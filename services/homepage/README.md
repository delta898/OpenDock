# Homepage

Default Homepage dashboard service for the home server stack.

This service uses gethomepage's official Docker image and keeps dashboard configuration in `services/homepage/config/`.

## Setup

Set the main stack domain in `common.env`:

```sh
STACK_DOMAIN=example.com
HOMEPAGE_SUBDOMAIN=home
```

The default public URL becomes:

```text
https://home.example.com/
```

Then start the stack:

```sh
make up homepage
make up gateway
```

## Image Policy

- Homepage defaults to `v1.13.2`.
- Versions live in `.env`, not `compose.yml`.
- Avoid `latest` tags.

## Config

Homepage is configured with YAML files under:

```text
services/homepage/config/
```

The default dashboard links to WordPress, n8n, and Uptime Kuma using the shared `STACK_DOMAIN` and service subdomain settings.
