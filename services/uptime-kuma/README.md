# Uptime Kuma

Default Uptime Kuma service for the home server stack.

This service uses Uptime Kuma's official Docker image and stores persistent data in a Docker named volume.

## Setup

Set the main stack domain in `common.env`:

```sh
STACK_DOMAIN=example.com
UPTIME_KUMA_SUBDOMAIN=uptime
```

The default public URL becomes:

```text
https://uptime.example.com/
```

Then start the stack:

```sh
make up uptime-kuma
make up gateway
```

## Image Policy

- Uptime Kuma defaults to `2.4.0`.
- Versions live in `.env`, not `compose.yml`.
- Avoid `latest` tags.

## Data

Uptime Kuma stores monitors, notification settings, status pages, and local app data under:

```text
uptime_kuma_data
```

This is a Docker named volume managed by Compose.
