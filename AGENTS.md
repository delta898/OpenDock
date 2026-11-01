# OpenDock Agent Guidance

## Zero-config service workflow

OpenDock is a multi-service platform. Keep the common path simple: when a
service can be started safely, `./opendock launch <service>` should prepare
its prerequisites and bring it up without requiring users to discover
service-specific setup commands.

- Run only prerequisites that are missing. Detect completed setup reliably and
  skip it on later launches; repeated commands must not restart interactive
  wizards or overwrite user data.
- `./opendock setup <service>` is the detailed path for reviewing configuration
  and completing first-run service setup. It should cover the same required
  preparation as launch, so users do not need an extra hidden command.
- Do not re-run a completed interactive first-run wizard just because a user
  asks to review OpenDock-managed settings. If the upstream service provides a
  useful repeatable configuration flow, expose it as an explicit
  service-specific maintenance command while keeping first-run setup automatic.
- Ask the user only for values that cannot be inferred safely, such as their
  domain or an external provider choice. Generate machine-owned secrets and
  use safe defaults where appropriate.
- Treat shared infrastructure as a normal OpenDock platform prerequisite.
  Start it when required and keep the order explicit in the CLI output.
- Keep implementation steps internal when they are not useful as independent
  user commands. If a prerequisite cannot be automated, fail before changing
  service state and print the next useful command or action.
- Apply this workflow to services where it is safe and practical; do not force
  the same prompts or setup behavior onto services that do not need them.

## Configuration ownership

Keep defaults and machine-local effective values separate. Tracked defaults use
`.env.default`; actual `.env` files are private overrides and secrets.

- Core, shared-infrastructure, and shared-concern defaults live in
  `config/core.env.default`, `config/infra.env.default`, and
  `config/shared/<concern>.env.default`. Their private effective files use the
  same paths without `.default`.
- Every service owns `services/<service>/.env.default` for tracked runtime
  defaults, including image tags, and `services/<service>/.env` for local
  overrides and secrets. Renovate tracks `.env.default` files. The ignored
  local `.env` is not scanned.
- Keep route maps and external provider credentials in their dedicated files;
  do not fold them into the application environment layers.

Register every new setting's owner in `scripts/opendock_settings.py` and add it
to the matching `.env.default` template. Setup, secret
generation, validation, route resolution, Compose invocations, and service
post-launch scripts must read the shared settings loader rather than parsing an
individual config file on their own. Pass Compose interpolation files
explicitly and in the documented order;
Compose `env_file:` is not a substitute for `--env-file`.

Do not add new values to legacy root `common.env`. Its one-time migration must
preserve known values, keep a restrictive backup, and stop without changing the
legacy file if it encounters an unregistered key. Migrate old private
`config/services/*.env` files to service-owned `.env` files with restrictive
backups. Keep actual `config/*.env` and `services/*/.env` files private and out
of Git while syncing the tracked defaults.
The former tracked `infra/.env` held shared image defaults; move them to
`config/infra.env.default` and migrate non-default host values to
`config/infra.env` before removing the old file.
The former tracked `gateway/.env` held Caddy and port defaults; keep them in
`config/gateway.env.default` and migrate non-default host values to
`config/gateway.env` before removing the old file.
During the one-time service defaults migration, remove only local values that
match either the new `.env.default` or the previous tracked service `.env`
default recorded in `config/migrations/service-env-v1.json`; preserve other
overrides and keep a restrictive backup of any rewritten file.

## Service removal and reset behavior

Every service must have a clear removal contract that mirrors the resources
OpenDock provisions for it. `stop` stops running containers; `down` removes
containers while preserving persistent data. `remove <service>` means complete
removal (`all`) by default and must always ask for confirmation before making
changes.

- Before confirmation, show the exact service-owned resources that would be
  removed: containers, images, named volumes, bind-mounted data paths, service
  database/schema, service-specific configuration, and public routes as
  applicable.
- Treat resources according to ownership. Never remove shared infra databases
  or volumes, global OpenDock configuration such as the primary domain,
  resources belonging to another service, or user content outside the selected
  service's declared removal scope.
- Do not infer that every file under `services/<name>/data/` is disposable.
  Each service must identify generated state, caches, and user-owned content so
  the removal plan can describe their effect accurately.
- Services that use shared databases must remove only their own database or
  schema through a service-aware operation; removing the shared database
  volume is not a service reset.
- A new service must declare how its service-scoped settings, containers,
  images, persistent data, database objects, and routes are removed. Reuse the
  common `remove <service>` interface and keep service-specific cleanup logic
  behind that interface.
- Roll out removal support service by service. Enable a service only after its
  removal contract has been audited and registered; reject unsupported targets
  instead of guessing their cleanup behavior. Do not call the feature complete
  until every existing service has been audited.
- Prefer deriving containers, images, and Compose named volumes from the
  service's Compose project. Require explicit service metadata for bind-mounted
  paths, shared-database objects, public routes, and any user content that must
  be retained or needs a separate warning.
- If removal scopes are added, allow narrower selections for individual
  resource classes. The no-scope command remains the complete service removal
  and must not silently degrade to container-only removal.
- Refuse removal without confirmation in non-interactive use. Do not add a
  confirmation bypass that defeats the explicit-confirmation requirement.

## Development journal and BlogGenius seeds

OpenDock is developed together with the user, who may turn meaningful parts of
that work into articles with BlogGenius. Treat the reasoning, failed attempts,
tradeoffs, operational lessons, and user-facing outcomes as potential material,
not only the final code.

The durable backlog for these ideas is `docs/blog-seeds.md`. Read that file
before proposing or recording a seed. At a natural checkpoint, update an
existing entry with better evidence or add a new entry when the subject is
distinct and substantial. The conversation suggestion is a short notification;
the document is the detailed source of truth. Mention material backlog changes
to the user, but do not turn every minor update into a blog suggestion.

Proactively suggest blog seeds at a natural checkpoint even when the user does
not explicitly request them. Good checkpoints include:

- completion or merge of a substantial feature;
- resolution of a difficult, multi-stage failure or intermittent problem;
- agreement on an architecture, security boundary, or compatibility strategy;
- a migration that reveals reusable operational lessons;
- repeated confusion that leads to a clearer command, workflow, or UX convention;
- testing that confirms or disproves a non-obvious assumption.

Do not interrupt active debugging merely to suggest content. Accumulate related
ideas and present them together when the current milestone is complete, the
conversation naturally pauses, or several strong lessons have emerged. Skip
routine edits, formatting-only work, ordinary commits, and minor fixes unless
they complete a larger story. Avoid repeatedly proposing substantially the same
topic.

Keep the suggestion lightweight and useful as BlogGenius input. Normally offer
two to five seeds in Korean using this shape:

```text
블로그 글감 제안

- 주제: <working title or angle>
  간단 내용: <problem, notable attempts or decision, lesson, result, and usage>
```

Prefer topics that teach a transferable idea while remaining grounded in the
actual OpenDock work. Strong seeds usually include several of these elements:

- what the user originally expected or did not yet know;
- the symptom and why the first explanation was incomplete;
- failed attempts and the evidence that changed the direction;
- the final design and its tradeoffs;
- how OpenDock's zero-config philosophy influenced the result;
- verification status, operational cautions, and concrete usage commands;
- a lesson applicable to other self-hosted or Docker-based projects.

Entries in `docs/blog-seeds.md` should be detailed enough to prevent a generic
article. For each seed, record:

- a working topic and the specific reader question or angle;
- the OpenDock-specific context, symptoms, attempts, decisions, and tradeoffs;
- evidence such as related commits, files, commands, or generalized log clues;
- what was verified locally, what the user verified in a real environment, and
  what remains unverified;
- concrete lessons and cautions that BlogGenius should preserve.

Focus detail on our distinctive experience and reasoning. Do not spend many
lines restating general Docker, Git, reverse-proxy, or Supabase background that
BlogGenius can supply. Merge overlapping entries instead of creating several
thin variations. Use backlog states `seed`, `ready`, `drafted`, and `published`;
do not advance an entry beyond `seed` without the user's direction. When an
article is drafted or published, preserve the seed and add its status and link
instead of deleting the historical material.

Maintain editorial and security discipline:

- Do not invent events, test results, motivations, or lessons.
- Distinguish locally verified results, user-verified results, and work still
  awaiting a real-environment test.
- Never include secret values, private keys, credentials, personal domains,
  private hostnames, account identifiers, or sensitive logs. Generalize them.
- Do not frame an unresolved incident as a success story.
- Keep titles and summaries distinct enough that each seed can become a useful
  standalone article; combine overlapping ideas instead of padding the list.
- Treat commit messages as evidence pointers, not as complete history. Inspect
  the relevant diff and documentation before recording detailed claims.
- Respect the user's request to defer, shorten, or stop journal suggestions.

Suggesting a seed does not authorize creating a full article, modifying a
BlogGenius project, publishing content, or sending data to another service.
Perform those actions only when the user explicitly requests them.
