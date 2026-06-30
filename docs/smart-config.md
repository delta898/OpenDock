# Smart Config Design Notes

This document captures the next configuration direction for OpenDock. It is a working design note so the work can continue from another machine without losing context.

## Current Context

OpenDock now supports generated secrets through:

```sh
make secrets
make secrets mastodon
make launch mastodon
```

The implementation lives in:

```text
scripts/opendock-secrets.py
scripts/check-config.py
Makefile
common.env.example
```

Current behavior:

- `make check-config` is read-only.
- `make secrets [target]` fills generated secrets in `common.env`.
- `make up`, `make services`, and `make launch` run the generator before validation.
- Existing real values are kept.
- Empty or placeholder secret values are generated.
- `common.env` is backed up under `backups/common-env/` before mutation.

This gives a good zero-config baseline. The first smart-config step now uses `make setup`: ask only for values that genuinely need user intent, while continuing to generate machine secrets.

## Goal

Interactive setup command:

```sh
make setup
make setup mastodon
make setup nextcloud
```

`make setup` guides the user through required and useful choices, while continuing to generate machine secrets transparently.

The desired user experience:

```text
make setup mastodon

STACK_DOMAIN: gongzza.com
MASTODON_SUBDOMAIN [social]:
MASTODON_ADMIN_USERNAME [opendock]:
MASTODON_ADMIN_EMAIL: delta@example.com
MASTODON_ADMIN_PASSWORD [auto-generate]:

Generated secrets:
  POSTGRES_ADMIN_PASSWORD
  MASTODON_DB_PASSWORD
  MASTODON_SECRET_KEY_BASE
  MASTODON_OTP_SECRET
  MASTODON_VAPID_PRIVATE_KEY
  MASTODON_VAPID_PUBLIC_KEY

Updated common.env.
Backup: backups/common-env/common.env.<timestamp>.bak
```

Secrets should not be printed. For login credentials that users need later, point them to `common.env`.

## Config Classes

Use four explicit classes.

### required-user

Values that cannot be guessed safely and require user input.

Examples:

```text
STACK_DOMAIN
MASTODON_ADMIN_EMAIL
CLOUDFLARE_API_TOKEN       when enabling Cloudflare sync
CLOUDFLARE_TUNNEL_ID       when enabling Cloudflare sync
SMTP credentials           when enabling outbound email
```

Rules:

- Do not auto-generate.
- Prompt without a default unless a real existing value is present.
- Empty input is invalid.
- Existing real values can be shown as defaults for confirmation.

### generated-secret

Values that users do not need to choose and should usually not see.

Examples:

```text
MARIADB_ROOT_PASSWORD
POSTGRES_ADMIN_PASSWORD
WORDPRESS_DB_PASSWORD
NEXTCLOUD_DB_PASSWORD
IMMICH_DB_PASSWORD
MASTODON_DB_PASSWORD
MASTODON_SECRET_KEY_BASE
MASTODON_OTP_SECRET
MASTODON_ACTIVE_RECORD_ENCRYPTION_*
MASTODON_VAPID_PRIVATE_KEY
MASTODON_VAPID_PUBLIC_KEY
```

Rules:

- Do not prompt.
- Generate when missing or placeholder.
- Keep existing real values.
- Print only key names in summaries.

### initial-credential

Values that may be generated but are directly used by a person for initial login.

Examples:

```text
NEXTCLOUD_ADMIN_PASSWORD
MASTODON_ADMIN_PASSWORD       proposed
```

Rules:

- Prompt with `[auto-generate]`.
- Enter means generate.
- User input is accepted and stored.
- Auto-generated values should be copy/paste friendly, around 20 characters, and avoid easily confused characters.
- Do not echo password values in summaries.
- Explain where to find the value.
- Explain whether changing `common.env` later affects an installed app.

Important known behavior:

- `NEXTCLOUD_ADMIN_PASSWORD` is used only during first successful Nextcloud installation. Changing `common.env` later does not reset the installed admin password.
- `MASTODON_ADMIN_PASSWORD` is used only when OpenDock creates the first Mastodon owner account. Changing `common.env` later does not reset an existing Mastodon account.

### defaulted-choice

Values that have good defaults but should be easy to override.

Examples:

```text
WORDPRESS_SUBDOMAIN=blog
NEXTCLOUD_SUBDOMAIN=cloud
IMMICH_SUBDOMAIN=photos
JELLYFIN_SUBDOMAIN=media
MASTODON_SUBDOMAIN=social
MASTODON_ADMIN_USERNAME=opendock     proposed
```

Rules:

- Prompt with `[default]`.
- Enter uses the default.
- User input overrides the default.
- Existing real values should be shown as the current default.

## Command Boundaries

Keep these command roles separate.

```text
make setup [target]
  Interactive smart setup. May ask questions and update common.env.

make secrets [target]
  Non-interactive generated-secret fill. Should not ask questions.

make check-config [target]
  Read-only validation. Should never change files.

make launch [target]
  Non-interactive start workflow. It may fill generated-secret values, but it should not ask questions.
```

Important decision:

`make launch` should remain non-interactive. This preserves predictable automation and remote usage. If required-user values are missing, it should fail with a friendly message that points to `make setup [target]`.

## Target Behavior

`make setup` without a target should configure `all`.

Suggested target resolution:

```text
make setup
  global + infra + every service

make setup mastodon
  global + infra values needed by Mastodon + Mastodon fields

make setup nextcloud
  global + infra values needed by Nextcloud + Nextcloud fields
```

Global fields should be asked once, not once per service.

## Proposed Field Registry

A central registry should drive `config`, `secrets`, and eventually validation hints.

Possible shape:

```python
CONFIG_FIELDS = {
    "global": [
        Field("STACK_DOMAIN", kind="required-user"),
    ],
    "mariadb": [
        Field("MARIADB_ROOT_PASSWORD", kind="generated-secret"),
    ],
    "postgres": [
        Field("POSTGRES_ADMIN_USER", kind="defaulted-choice", default="opendock"),
        Field("POSTGRES_ADMIN_PASSWORD", kind="generated-secret"),
    ],
    "mastodon": [
        Field("MASTODON_SUBDOMAIN", kind="defaulted-choice", default="social"),
        Field("MASTODON_ADMIN_USERNAME", kind="defaulted-choice", default="opendock"),
        Field("MASTODON_ADMIN_EMAIL", kind="required-user"),
        Field("MASTODON_ADMIN_PASSWORD", kind="initial-credential"),
        Field("MASTODON_DB_PASSWORD", kind="generated-secret"),
        Field("MASTODON_SECRET_KEY_BASE", kind="generated-secret"),
        Field("MASTODON_OTP_SECRET", kind="generated-secret"),
        Field("MASTODON_VAPID_PRIVATE_KEY", kind="generated-secret"),
        Field("MASTODON_VAPID_PUBLIC_KEY", kind="generated-secret"),
    ],
    "nextcloud": [
        Field("NEXTCLOUD_SUBDOMAIN", kind="defaulted-choice", default="cloud"),
        Field("NEXTCLOUD_DB_PASSWORD", kind="generated-secret"),
        Field("NEXTCLOUD_ADMIN_PASSWORD", kind="initial-credential"),
    ],
}
```

This registry can start inside `scripts/opendock-config.py` or be split into a shared Python module later. Keep it simple first.

## Mastodon Admin Account Direction

Need:

1. The owner wants to join their own Mastodon server.
2. Public signup should stay closed.
3. Admin-created or admin-invited users are preferred.

Desired behavior:

```text
make launch mastodon
  -> ensure generated secrets
  -> start Mastodon
  -> if no owner exists, create owner account
  -> set the new owner password from MASTODON_ADMIN_PASSWORD
  -> show login guidance
```

However, this should be designed carefully:

- `make launch` should stay non-interactive.
- `make setup mastodon` should collect `MASTODON_ADMIN_EMAIL`.
- If Mastodon admin fields are missing, `make launch mastodon` should not prompt. It should say to run `make setup mastodon`.
- If an owner already exists, do nothing.
- Do not reset admin passwords automatically.

Implemented entrypoint:

```sh
make setup mastodon
make launch mastodon
```

The account helper is service-owned and lives at `services/mastodon/opendock-post-launch.py`, called by the generic launch post-hook.

Still to verify:

- Verify the Rails runner owner detection and password assignment against a fresh Mastodon instance.
- Whether separate account/password-reset helpers are worth adding later.

Current product opinion:

- Email is required for Mastodon admin setup.
- Defaulting to `admin@STACK_DOMAIN` is convenient but not ideal, because the owner may need password recovery or notifications later.
- Prefer `MASTODON_ADMIN_EMAIL` as required-user in `make setup mastodon`.

## Remaining Implementation Plan

Completed first step:

- `scripts/opendock-config.py`
- `make setup [target]`
- basic field registry for global, infra, and service fields
- prompt helpers for required input, defaulted input, initial credentials, and silent generated secrets
- high-signal summaries that do not print secret values
- `scripts/check-config.py` suggestions for `make setup [target]`
- README quick start update

Suggested next steps:

1. Verify owner detection and password assignment against a fresh Mastodon instance.
2. Decide whether separate account/password-reset helpers are worth adding later.
3. Consider Cloudflare setup later, perhaps as `make setup cloudflare`.
4. Add focused tests with temporary directories, similar to the manual checks already used for `opendock-secrets.py`.

## Open Questions

- Should `make setup` create `common.env` automatically if missing, or should the user still run `cp common.env.example common.env`? Current preference: create it automatically, matching `make secrets`.
- Should `make setup` support `--non-interactive` later? Current preference: not now; `make secrets` already covers non-interactive generated values.
- Should Cloudflare be included in `make setup` now? Current preference: later, perhaps as `make setup cloudflare` or a prompt asking whether to enable Cloudflare sync.
- Should additional Mastodon account management helpers be exposed later, and if so should they remain service-owned rather than top-level make commands?

## Safety Rules

- Never mutate `common.env` without a backup unless it was just created from `common.env.example`.
- Never print secret values in logs by default.
- Never rotate existing real secrets automatically.
- Never turn `make launch` into an interactive command.
- Keep `make check-config` read-only.
