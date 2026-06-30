# n8n

Default n8n service for the home server stack.

This service uses n8n's official Docker image and stores persistent data in a Docker named volume.

## Setup

Set the main stack domain in `common.env`:

```sh
STACK_DOMAIN=example.com
N8N_SUBDOMAIN=n8n
```

The default public URL becomes:

```text
https://n8n.example.com/
```

n8n receives this URL automatically as `WEBHOOK_URL`.

Outbound user-management email uses the common SMTP relay values in `common.env`:

```env
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=mailer@example.com
SMTP_PASSWORD=change-smtp-password
SMTP_FROM_ADDRESS=mailer@example.com
```

Use `make setup mail` to fill these values interactively. OpenDock maps them into n8n's official SMTP environment variables.

Then start the stack:

```sh
make up infra
make up n8n
make up gateway
```

## Image Policy

- n8n defaults to `2.26.8`.
- Versions live in `.env`, not `compose.yml`.
- Avoid `latest` tags.

## Data

n8n stores workflows, credentials, encryption keys, and local execution data under:

```text
n8n_data
```

This is a Docker named volume managed by Compose. It avoids host filesystem permission problems on Ubuntu Server.
