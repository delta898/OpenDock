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

The real `.sync.env` file is intentionally ignored by Git.

## Environment

Copy the example file before running infra services:

```sh
cp infra/.env.example infra/.env
```

Then edit `infra/.env` locally. Real `.env` files are intentionally ignored by Git.
