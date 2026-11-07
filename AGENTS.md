# OpenDock Agent Guidance

## Greenfield product redesign

The current target design is documented in
`docs/product-distribution.md` and its linked catalog/package, service
capability, and command/instance contracts. Newer user decisions recorded
there take precedence over this file wherever they conflict. In particular,
the old `bundles/` versus `extensions/` product split and signed-package
assumptions are not target requirements. Existing repository paths and code
remain useful references; do not preserve their interfaces for backward
compatibility. Keep the safety principles below—idempotent setup, scoped
configuration, explicit ownership, and confirmation for destructive work—when
translating them into the new design.

For all new product and documentation work, follow the current product rule:
there is no bundled-service category. New service source belongs in the separate
OpenDock-Services repository and is installed from the static catalog. References
below to `services/bundles/` describe legacy migration material only; they are
not instructions to add new services there. Package `update`, `search`, and
`install` are operational, while package setup, launch, and domain-scoped
instances remain unfinished.

## Repository split and service paths

OpenDock is the platform repository and does not ship application services as
bundles. All service source lives in the separate OpenDock-Services repository
under `services/extensions/<service-id>/`. Installed package releases live in
OpenDock under `services/extensions/<service-id>/releases/<version>`; keep
mutable per-instance state outside immutable release directories. Resolve
service paths through the catalog instead of constructing paths from IDs.

Any `services/bundles/` or old flat service trees still present in this checkout
are migration residue and must not be used for new work. The local, gitignored
`archive/` is preservation material only and must never be discovered, packaged,
or synced to a host.

## Git remote operations

Do not push commits, branches, or tags to any remote unless the user explicitly
requests the push. A request to commit, merge, or otherwise organize Git history
does not imply permission to push. This rule also applies when managing the
companion `OpenDock-Services` repository. Fetching remote state for a requested
Git operation is allowed; publishing local changes requires a separate,
explicit user request.

### `[cmd]` shorthand

When the user says `[cmd]`, treat it as an instruction to complete the local
Git workflow for the active feature branch:

1. Review the worktree and relevant diff, finish the requested work, and run
   the applicable verification before committing.
2. Commit the completed changes on the current feature branch. Do not create an
   empty commit when there are no changes to record.
3. Merge that branch into its parent branch. Use an explicitly named target if
   the user supplied one; otherwise use `dev` as the parent for feature work.
4. After confirming the merge succeeded, delete the source feature branch
   locally and leave the checkout on the parent branch.

This shorthand applies to both OpenDock and OpenDock-Services when the task
touches either or both repositories. Never delete `main`, `dev`, or
`release/*`. Delete a source branch only after Git confirms it is merged. If
the current branch is protected, the parent cannot be identified safely, or a
merge conflict prevents completion, stop before deleting anything and report
the specific blocker. `[cmd]` does not authorize pushing; the user must
explicitly ask to push.

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
- Installed services read tracked runtime defaults from their active package
  release and keep private effective settings outside that release under
  `config/extensions/` or the instance-owned config location. Renovate scans
  tracked `.env.default` files, never private `.env` files. Legacy bundle and
  flat service paths remain only during repository migration.
- Keep route maps and external provider credentials in their dedicated files;
  do not fold them into the application environment layers.

Register every new setting's owner in the supported settings interface and add
it to the matching `.env.default` template. Setup, secret generation,
validation, route resolution, Compose invocations, and service capabilities
must access configuration through that scoped interface rather than parsing
individual config files. Pass Compose interpolation files explicitly and in
the documented order;
Compose `env_file:` is not a substitute for `--env-file`.

For services with large user data, declare host storage mounts in the service
descriptor and make each location a service-owned setup field. Keep a safe
checkout-local default so launch remains zero-config. Use Compose bind mounts
with `create_host_path: false` so Compose does not create a missing source path
automatically. Validate that the configured directory exists and is accessible
before launch. OpenDock may create a missing checkout-local default under the
service's declared removal path; never auto-create a user-selected override.
On first launch, ask the user to accept the default or choose a custom location,
persist that choice privately, and do not repeat the prompt on later launches.
`setup <service>` must offer the same field for review or change.
Do not infer that a path is on an external disk: if an unmounted disk's
mount-point directory still exists on the system disk, OpenDock uses the path
the user configured. Document this behavior and declare removal ownership so
`purge` displays the exact location before deleting it. Keep databases and
other latency-sensitive state on their existing local storage unless the
service explicitly supports moving them.

Declare service-owned setup fields, required values, initial credentials, and
secret generator identifiers in the service's `opendock.toml`. Keep
application-specific secret bundles and validation rules in that service's
`opendock.py` capability. The common `setup`, `launch`, and `secrets` flows
must use the same secret coordinator: setup creates missing values while
configuring, launch creates missing values before checking configuration, and
`secrets` provides an explicit repair path. The common layer owns generic
generators, secure persistence, and consistent output; it must not enumerate
service-specific generator types, secret relationships, or validation rules.
Shared platform settings and shared setup groups belong to the corresponding
platform component descriptor (`infra/opendock.toml`, `gateway/opendock.toml`).
Services declare only the shared groups they require; config prompting, secret
generation, setup dependency validation, and platform setting ownership must
derive those shared declarations instead of keeping duplicate registries in
central scripts. Core settings and shared non-platform concerns belong in
`config/core.toml` and `config/shared/*.toml`; those descriptors own keys,
configuration files, and setup fields. The common settings interface discovers
their metadata rather than naming individual keys or files in Python.

Do not add new values to legacy root `common.env`. Its one-time migration must
preserve known values, keep a restrictive backup, and stop without changing the
legacy file if it encounters an unregistered key. Migrate old private
`config/services/*.env` files to service-owned private configuration with
restrictive backups. Keep actual `config/*.env` and service `.env` files
private and out of Git while syncing the tracked defaults.
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

## Service reset and purge behavior

Every service must have a clear removal contract that mirrors the resources
OpenDock provisions for it. `stop` stops running containers; `down` removes
containers while preserving persistent data. `purge <service>` means complete
removal (`all`) of the service's runtime resources by default and must always
ask for confirmation before making changes. The service definition remains
installed so the service can be set up and launched again. `uninstall` is a
separate package-code operation and must not delete runtime state implicitly.

- Before confirmation, show the exact service-owned resources that would be
  removed: containers, images, named volumes, bind-mounted data paths, service
  database/schema, service-specific configuration, and public routes as
  applicable.
- If a service has additional ignored secret/config files beyond `.env`, declare
  them under `removal.config_files`; back them up with restrictive permissions
  before deletion and list them in the plan.
- If a removable directory contains tracked source files that must stay in the
  checkout, declare each under `removal.preserve_paths`; show and preserve them
  while deleting the rest of the declared data path.
- Treat resources according to ownership. Never remove shared infra databases
  or volumes, global OpenDock configuration such as the primary domain,
  resources belonging to another service, or user content outside the selected
  service's declared removal scope.
- Do not infer that every file under a service's declared data directory is disposable.
  Each service must identify generated state, caches, and user-owned content so
  the removal plan can describe their effect accurately.
- Services that use shared databases must remove only their own database or
  schema through a service-aware operation; removing the shared database
  volume is not a service purge.
- Describe shared database adapters in the platform descriptor and each
  service's exact database/role keys in its removal descriptor. Refuse removal
  if another dependent service has no audited declaration or if configured
  database/role names collide.
- A new service must declare how its service-scoped settings, containers,
  images, persistent data, database objects, and routes are removed. Reuse the
  common `purge <service>` interface and keep service-specific cleanup logic
  behind that interface.
- Roll out removal support service by service. Enable a service only after its
  removal contract has been audited and registered; reject unsupported targets
  instead of guessing their cleanup behavior. Do not call the feature complete
  until every existing service has been audited.
- Prefer deriving containers, images, and Compose named volumes from the
  service's Compose project. Require explicit service metadata for bind-mounted
  paths, shared-database objects, public routes, and any user content that must
  be retained or needs a separate warning.
- If purge scopes are added, allow narrower selections for individual
  resource classes. The no-scope command remains the complete service purge
  and must not silently degrade to container-only removal.
- Refuse purge without confirmation in non-interactive use. Do not add a
  confirmation bypass that defeats the explicit-confirmation requirement.
- After every current service has an audited removal contract, verify all
  services from a clean, isolated host: configure, launch, repeat launch,
  inspect the purge plan, purge, and confirm service-owned resources are
  gone while shared infra and unrelated routes/data remain. Do not claim the
  purge rollout complete before this end-to-end pass.

## Command and service ownership

Keep common command workflows in the OpenDock CLI and service-specific
application knowledge in `OpenDock-Services/services/extensions/<name>/`.
The CLI owns target resolution, shared configuration
services, prerequisite ordering, common confirmation, Compose invocation,
gateway/Cloudflare routing, and consistent progress/errors.
Services own their setup fields, first-run preparation, custom readiness,
application migrations, and exact cleanup scope. A new service must not require
a service-name conditional in the central CLI for these behaviors.

Use declarative capability metadata for facts and safe common operations; use
optional service hooks for procedures that need application knowledge. Keep
hooks idempotent, scoped to the selected service, and integrated through the
common workflow. A hook must not bypass common validation, confirmation, shared
prerequisite ordering, or public route handling. Absent optional capabilities
should require no empty script. Keep service commands beside their contribution
under `commands/` and align new lifecycle hooks with
`docs/command-architecture.md` rather than creating a parallel interface.
Declare every lifecycle hook in the service descriptor; the CLI must not infer
capabilities from helper filenames. Routable services must declare their
subdomain setting and Caddy handler in descriptor routing metadata. Shared
database object operations belong to adapters registered by the infra
descriptor, while each service declares only its own database and role keys.
Optional cross-service setup such as SMTP belongs in `config/shared/*.toml`;
services opt into its setup prompt through descriptor metadata. Declining an
optional prompt must never block service startup, and the user must have a
clear explicit command to configure it later.

Design and roll out the capability contract across command families instead of
implementing one special case in isolation. Pilot it on a service with real
preparation behavior and a simple service, then migrate setup, launch, and
removal incrementally. Keep the user-facing top-level command grammar common.

Treat each service as an in-repository extension unit with a stable service ID,
a versioned descriptor, and only the optional capability handlers it needs.
Discovery must not require a second central service registration list. Keep
descriptor schema version separate from capability API version; reject
unsupported required versions before changing service state. Removing a
service's runtime data with `purge` is separate from deregistering its code.
Deleting or disabling a service definition must never implicitly delete
containers, volumes, configuration, or user data.
Keep service command summaries, details, and examples in that service's
descriptor beside its executable command files. The common dispatcher should
render the shared help format without a central per-service command table.

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
