# Service Descriptor and Capability API v1

This document defines the proposed v1 contract between the OpenDock platform
and separately distributed service packages. It replaces the earlier sketch
with concrete descriptor fields, ownership rules, lifecycle stages, and hook
behavior. It is a design contract; it does not claim these interfaces are
implemented.

## Goals and non-goals

- Install one service package, then create multiple independent instances of
  that service.
- Keep service-specific names, fields, and application knowledge out of core.
- Let core perform safe common operations from declarative metadata.
- Provide narrow optional hooks for application procedures the platform cannot
  correctly generalize.
- Reject unsupported required schema/capability versions before changing
  installed package or instance state.

Version 1 is for curated OpenDock service packages. It is not a sandboxed,
arbitrary third-party plugin system. A capability handler can execute code as
the local OpenDock user. SHA-256 checks that downloaded bytes match the
catalog; it does not authenticate the publisher if the catalog and package
are both replaced.

## Package and instance ownership

The package is the immutable, versioned integration definition: descriptor,
Compose files, defaults/templates, optional capability handlers, commands,
routing resources, and documentation. A site instance is a deployment created
from that package. It references a platform-owned base domain and owns its
private settings/secrets, Compose project identity, assigned route, and
persistent data.

The initial contract requires **isolated multiple instances** for every
service. A package may be installed once and used for `a.com`, `b.com`, and
additional instances. A registered base domain is platform-owned and can be
referenced by instances of several services. For example, WordPress and n8n
may both attach to `a.com`, using distinct route hostnames. Within one service
package, v1 allows at most one instance per base domain. Instance resources
must not collide or be shared unless the descriptor explicitly declares a
platform-shared dependency. A service that cannot run two isolated instances
does not meet this contract.

Instance state lives outside immutable release directories. Package upgrade
must preserve every instance. `purge` removes one instance according to its
declared ownership contract. `uninstall` removes package code only after no
instances remain.

## Version identities

Keep these versions independent:

1. `descriptor_schema_version`: syntax and meaning of the descriptor.
2. `capability_api_version`: handler/context/result contract. Use SemVer; a
   breaking change increments the major version.
3. `package_version`: release version of this service integration.
4. OpenDock platform version: CLI and host-runtime release.
5. Catalog schema version: format of the static catalog JSON.

V1 requires `descriptor_schema_version = 1` and capability API `1.x`. A service
declares the exact required API major; the catalog declares the compatible
OpenDock version range and supported host targets. The installer validates
catalog metadata and the package descriptor agree before activation.
Unsupported required versions, unknown required fields, invalid handler
declarations, and invalid package contents fail before installation is made
visible.

## Descriptor v1 proposal

The canonical filename is `opendock.toml`. Field names below are the proposed
v1 spelling, subject to one review before implementation:

```toml
descriptor_schema_version = 1
service_id = "example-cms"
package_version = "1.0.0"
display_name = "Example CMS"
summary = "Publish and manage a website"
capability_api_major = 1
supported_hosts = ["linux"]

[runtime]
kind = "compose"
compose_file = "compose.yml"

[instances]
model = "isolated-multiple"
domain_binding = "one-registered-base-domain"
unique_by = ["primary_domain"]

[[settings.fields]]
id = "site.title"
scope = "instance"
type = "string"
required = true
compose_env = "EXAMPLE_CMS_SITE_TITLE"

[[settings.fields]]
id = "site.admin_password"
scope = "instance"
type = "secret"
required = true
generator = "password-url-safe"
compose_env = "EXAMPLE_CMS_ADMIN_PASSWORD"

[[settings.fields]]
id = "site.jwt_keyset"
scope = "instance"
type = "secret"
required = true
generator = { kind = "capability", id = "jwt-keyset" }
compose_env = "EXAMPLE_CMS_JWT_KEYSET"

[[settings.fields]]
id = "storage.content_path"
scope = "instance"
type = "host-path"
required = true
default = "./data/content"
compose_env = "EXAMPLE_CMS_CONTENT_PATH"

[[dependencies]]
component = "database.postgresql"
scope = "shared"
needed_for = ["setup"]

[routing]
mode = "http"
compose_service = "web"
container_port = 8080
hostname_pattern = "{subdomain}.{domain}"
subdomain_setting = "route.subdomain"
handler_file = "routing/example-cms.caddy"

[[storage.mounts]]
id = "content"
setting = "storage.content_path"
container_path = "/srv/content"
access = "read-write"
ownership = "instance-user-data"

[removal]
compose_project = "instance"
config_files = [".env"]

[[removal.resources]]
kind = "bind-path"
id = "content"
setting = "storage.content_path"
policy = "delete-after-confirmation"

[capabilities.setup]
handler = "opendock.py:setup"
requires = ["database.schema"]
settings = ["site.title"]

[capabilities.prepare]
handler = "opendock.py:prepare"

[capabilities.readiness]
handler = "opendock.py:readiness"

[capabilities.post_start]
handler = "opendock.py:post_start"

[capabilities.validate_config]
handler = "opendock.py:validate_config"

[capabilities.plan_secrets]
handler = "opendock.py:plan_secrets"

[capabilities.generate_secrets]
handler = "opendock.py:generate_secrets"
setting_ids = ["site.jwt_keyset"]

[capabilities.runtime_environment]
handler = "opendock.py:runtime_environment"
environment_keys = ["EXAMPLE_CMS_ENGINE_MODE"]

[capabilities.upgrade]
handler = "opendock.py:upgrade"
reversible = false

[capabilities.purge]
handler = "opendock.py:purge"
```

This example illustrates ownership and shape; the exact database adapter IDs,
generic secret generator IDs, route format, and removal policies need final review.
The contract is strict: unknown fields fail validation rather than being
silently ignored. Optional metadata may be added compatibly under schema v1
only when older clients can safely ignore it.

### Descriptor sections

- **Identity:** stable `service_id`, package version, display/help metadata.
- **Compatibility:** required capability API major and supported host targets.
- **Runtime:** supported runtime kind and relative Compose definition path.
- **Instances:** v1 isolation guarantee and primary-domain behavior.
- **Settings:** stable setting IDs, owner scope, type, required/default rules,
  secret handling, and explicit Compose environment mapping.
- **Dependencies:** platform component/adapter identifiers and lifecycle stages
  that need them. Service names are not embedded in the platform.
- **Routing:** optional routability, Compose target, port, and package-owned
  handler/template. The platform validates and applies public routes.
- **Storage/removal:** service-owned host paths, config, shared database
  objects, route ownership, and what purge removes or preserves.
- **Capabilities:** explicit declarations mapping supported hook names to
  handler entry points and required platform adapters.
- **Commands:** optional per-service commands with descriptor-owned help and
  examples; dispatch remains common.

Compose project names and container/network aliases are generated per
instance by OpenDock. Service Compose files must not hard-code global
`container_name` values. For routable instances, the descriptor names the
Compose service and port; OpenDock supplies a unique network alias and the
common route layer maps the selected domain to that instance. A service-owned
handler/template may express app-specific HTTP behavior, but may not manage
Cloudflare, global DNS, or another instance's route.

The platform owns the registered base-domain record. Each service instance
declares its derived public hostname (for example, `blog.a.com` from
`blog` + `a.com`). OpenDock rejects hostname collisions across all services
and instances. Purging an instance removes only its route assignment; it never
deletes the shared base-domain record. A base domain cannot be removed while
any service instance references it.

Setting scopes are `platform`, `package`, or `instance`. Prefer `instance` for
site-specific values. `package` is only for a value genuinely shared by every
instance of one installed package; it must not be used for a value that could
cause cross-site data or credential sharing. Services cannot own platform
scope fields; those belong to platform descriptors.

### Host storage and removal ownership

A service with large/user-owned data declares the host mount and its path as an
instance setup field. On first interactive setup, the user accepts the safe
checkout-local default or selects an existing custom directory; OpenDock saves
the choice and does not prompt again unless the user reviews/changes it through
setup. The platform may create a missing declared checkout-local default under
the service's removal scope. It never auto-creates a missing user-selected
path. Validate existence and access before launch; do not infer that a path is
on a mounted external disk just because of its spelling. The removal plan must
show the exact configured path.

Compose named volumes belong to the instance's Compose project and can be
derived by common code. The descriptor must explicitly state bind-mounted
paths, service database/schema/role objects in shared infrastructure, extra
config files, route ownership, and user data to preserve. It must not treat
every file under a service directory as disposable. `purge` is complete
instance cleanup by default, with a precise pre-change plan and explicit
confirmation; unsupported ownership is a hard error. Shared infra objects and
the registered base domain are never removed by purging one instance.

## Capability API v1

Capabilities are optional. A service declares only the operations it needs; a
missing capability has common semantics and does not need an empty script.
The service descriptor—not a helper filename—declares each operation and its
handler. Capability names below are generic and contain no service IDs:

| Capability | Called by | Contract |
| --- | --- | --- |
| `validate_config` | `check-config`, `setup`, and `launch` before side effects | Optional. Receives scoped settings and returns typed issues. Use descriptor constraints for validations the common engine can express. |
| `plan_secrets` | Common secret coordinator before generation | Optional. Expands selected keys into an app-specific related secret group. It may not write values. |
| `generate_secrets` | Common secret coordinator when a declared custom generator is needed | Optional. Returns generated values; the common coordinator validates and securely persists them without printing. |
| `runtime_environment` | Before Compose rendering for an instance | Optional. Returns validated computed environment values. Prefer declarative runtime fields when possible; never return values for another instance. |
| `setup` | `setup <service> --domain <domain>` and incomplete setup inside `launch` | Optional. Performs setup requiring actual platform resources, such as creating an instance-owned database/schema. Configuration-only services omit it. Declared `requires` adapters start first. Idempotent and non-interactive. |
| `prepare` | `launch`, after config/setup checks, before target runtime start | Optional. Idempotent, non-interactive per-instance preparation required before start. Must not repeat an upstream interactive wizard merely to review settings. |
| `post_start` | `launch`, after Compose starts and before route publication | Optional. Performs a declared app-specific post-start action. Must be idempotent and report incomplete state; it cannot bypass common route publication. |
| `readiness` | Future `launch` stage, after post-start actions and before route publication | Planned, not currently supported. It will check application readiness and return a typed ready/not-ready result without changing global routes. |
| `upgrade` | Explicit `upgrade` when a service migration procedure is declared | Optional. Receives from/to package versions and the selected instance. Must declare reversibility and recovery guidance. The platform does not promise rollback after an irreversible data migration. |
| `purge` | `purge`, only after the common removal plan is displayed and confirmed | Optional. Removes only descriptor-declared resources using scoped adapters. Cannot broaden the confirmed plan. |

The supported launch hooks run at distinct points:

| Hook point | Type | Runs when | If absent |
| --- | --- | --- | --- |
| `lifecycle.messages.pre_prepare` | Informational message | After target resolution and before setup, secret, storage, or prerequisite preparation | No message is printed |
| `lifecycle.messages.post_prepare` | Informational message | After setup/configuration, storage validation, shared prerequisites, and `prepare` action succeed | No message is printed |
| `prepare` | Action capability | After shared prerequisites start, before the service Compose project starts | No action runs |
| `lifecycle.messages.pre_start` | Informational message | Immediately before starting the service Compose project | No message is printed |
| `post_start` | Action capability | After Compose reports running/healthy, before gateway and route publication | No action runs |
| `lifecycle.messages.post_start` | Informational message | After Compose start and the `post_start` action succeed | No message is printed |
| `lifecycle.messages.pre_launch` | Informational message | Immediately before gateway reload and public route publication | No message is printed |
| `lifecycle.messages.post_launch` | Informational message | After gateway reload and public route publication succeed | No message is printed |
| `readiness` | Planned action capability | Not implemented; intended after `post_start`, before route publication | Not available yet |

Compose startup success does not mean the application is ready unless its
Compose health check actually measures that readiness. A service's
`messages.post_launch` must not claim otherwise.

This preserves useful operations already exercised by the current repository
(`runtime_environment`, secret planning/generation, config validation,
`prepare`, and post-start actions) while adding the missing setup, readiness,
upgrade, and purge contracts. It does not preserve their current signatures or
implementation paths. A new optional capability can be additive within API
major 1; changing an existing capability's meaning requires a new API major.

For secrets, a field may name a platform-owned generic generator or use
`{ kind = "capability", id = "..." }` for a service-specific generator. The
common coordinator treats that capability ID as opaque, expands related keys
through optional `plan_secrets`, asks `generate_secrets` for values, validates
that the returned keys are declared for the capability, and securely persists
them. Core does not add service-specific generator branches.

Lifecycle messages do not require executable capability code. A service may
declare any subset of the six `[lifecycle.messages]` stages. The common
dispatcher prints a pre-stage message just before that phase and a post-stage
message only after success. Messages are informational and cannot change the
workflow result. Action stages remain optional capabilities: `prepare` handles
service preparation after shared prerequisites, and `post_start` handles
app-specific work after Compose startup but before public route publication.
A service with no declaration or capability is skipped without a placeholder
handler.

The three phases have fixed meanings: **prepare** resolves required setup,
secrets, storage, shared prerequisites, and service preparation; **start**
starts the service Compose project and waits for its declared health condition;
**launch** applies gateway configuration and publishes the public route. If no
Compose healthcheck measures application readiness, successful `start` only
means the container is running. A service may not imply app readiness in its
messages unless it declares a readiness mechanism; that capability is planned
but not implemented yet.

### `setup` and prerequisite behavior

Configuration is the default setup behavior. If the descriptor has no
`capabilities.setup`, `setup` validates and saves settings without starting
containers or shared infrastructure. If the service declares a setup hook and
names required adapters, OpenDock starts only those prerequisites, in common
platform order, then invokes the hook. It reports each action. The hook is
scoped to one instance and must not start unrelated services or alter global
settings. This is the only reason service setup automatically starts actual
infrastructure; a declaration of ordinary config fields alone never starts it.
The prompt engine, not the hook, owns interactive input; capability hooks are
non-interactive.

The hook declaration lists the setting IDs it consumes. The common workflow
records setup completion against the instance, package release, and revision
of those inputs. Changing one of those settings or upgrading the package
invalidates the marker. Re-running `setup` to review unrelated settings does
not repeat a first-run wizard. A declared setup hook must be safe to re-check
and idempotent; it may repair its own incomplete state. Launch invokes it only
when its setup state is incomplete or invalidated.

### Handler context and results

Every hook receives a typed context with only:

- OpenDock and capability API versions;
- service ID and package version;
- selected instance ID and primary domain, if any;
- the service's declared settings through scoped accessors;
- only the platform adapters declared for that capability;
- a redacting logger and a per-instance state/data path abstraction.

Do not pass the entire process environment, all platform settings, arbitrary
Docker access, or another service's context as a convenience. Adapter methods
are narrow operations (for example, create/check this declared database
object), not an unrestricted platform shell. This reduces accidental coupling;
because handlers are ordinary local code, it is not a security sandbox.

Each capability returns a dedicated typed value (`ValidationResult`,
`SecretPlan`, `SecretValues`, `RuntimeEnvironment`, `OperationResult`, or
`ReadinessResult` as appropriate), not prose for core to parse. Lifecycle
operation results share this shape:

```text
status: complete | retryable | blocked
message: safe user-facing summary
next_action: optional documented OpenDock action
details: structured, non-secret diagnostics
```

The data contracts are intentionally small:

- `ValidationResult` contains issue IDs, severity, and safe messages.
- `SecretPlan` contains only additional declared setting IDs to generate
  together; `SecretValues` maps declared setting IDs to values.
- `RuntimeEnvironment` maps only descriptor-declared environment keys to
  strings. It cannot introduce undeclared Compose interpolation variables.
- `ReadinessResult` is `ready`, `retryable`, or `blocked`, with a safe summary.
- `OperationResult` is used for setup, prepare, post-launch, upgrade, and
  purge. Upgrade results also carry the declared migration/recovery outcome.

No result includes secret values. Common code checks each returned key and
value type before persistence or applying the next lifecycle stage.

Only the common workflow renders output, redacts secrets, maps status to exit
codes, and decides whether the next lifecycle stage may run. A `blocked` setup,
readiness, or post-launch result prevents final success and explains
remediation. Secret results are persisted only by the common secret
coordinator; config validation results are presented before service state
changes.

## Lifecycle orchestration

### Install package

1. Resolve a compatible catalog release.
2. Download and verify SHA-256 before extraction.
3. Validate archive paths, descriptor, required API major, handler declarations,
   Compose files, and package metadata in staging.
4. Atomically register the immutable package release.

Installation does not create a site, prompt for service settings, start
containers, or execute capabilities.

### Setup an instance

1. Resolve an installed package and create/select the instance identified by
   `(service_id, registered base domain)`.
2. Collect declared settings, create missing secrets through the common
   coordinator, validate the resulting configuration, and persist private
   values safely.
3. If no `setup` capability is declared, finish without runtime side effects.
4. If declared, start only its explicit prerequisite adapters and invoke its
   idempotent hook. Save successful completion for this package release.

### Launch an instance

1. Require an installed compatible package and select one instance by
   `(service_id, registered base domain)`.
2. Generate missing secrets through the common coordinator, using declared
   generators and optional `plan_secrets`/`generate_secrets` capabilities.
3. Ask optional `validate_config` for issues; block before runtime changes if
   required values are invalid.
4. Print optional `lifecycle.messages.pre_prepare`; complete incomplete
   `setup`, generate required secrets, and validate storage/configuration.
5. Start declared shared prerequisites, run optional `prepare`, then print
   optional `lifecycle.messages.post_prepare`.
6. Print optional `lifecycle.messages.pre_start`, resolve optional
   `runtime_environment`, render Compose, and start the target project; wait
   for its running/health condition.
7. Run optional `post_start`, then print optional
   `lifecycle.messages.post_start`. A future readiness hook will run here
   before the route is published.
8. Print optional `lifecycle.messages.pre_launch`, apply the descriptor-owned
   route, and publish external tunnel/DNS. After successful publication, print
   optional `lifecycle.messages.post_launch`. Report partial state precisely
   when public exposure is absent.

Core owns ordering, Compose, gateway, route publication, and output. The
service hook owns only application-specific decisions/operations.

### Upgrade package

Validate the new package fully before making it active. Preserve all instance
state and the prior package release. If an `upgrade` hook is required, run it
through a versioned migration plan and clearly state that a database migration
may not be reversible. Define backups, activation ordering, and failure recovery
per migration before enabling automatic upgrades for that service.

### Purge and uninstall

The descriptor must account for containers, images, named volumes, bind paths,
private config, service-owned database objects, and routes. The common layer
builds and displays the exact per-instance plan, requires explicit interactive
confirmation, and then invokes common cleanup and optional `purge`. Unsupported
or ambiguous ownership fails closed. Package uninstall is separate and refuses
while any instance remains.

## Compatibility and validation

Before state changes, validate:

- descriptor schema and required capability API major;
- host target against the package's declared supported hosts;
- package/service identity and version against the catalog;
- package compatibility with this OpenDock release;
- valid setting scopes/types/defaults and unique IDs;
- every dependency/adapter is supported and allowed at that lifecycle stage;
- declared hook name, entry point, file path, and handler signature;
- instance-scoped Compose project, environment, route, storage, and removal
  ownership references;
- no package attempts to claim platform-owned configuration or another
  instance's resources.

All validation output points to the package file and descriptor field. Install
and upgrade activation are atomic at the package-registry boundary. Runtime
operations are separately scoped to one instance.

Package installation checks handler references without importing executable
modules. Static validation can confirm the declared module/function exists;
callable signature and result checks occur immediately before invocation,
before that lifecycle step performs side effects.

## Decisions to close before implementation

- Confirm exact TOML property names and whether `opendock.toml` is the canonical
  package filename.
- Finalize setting types, defaults, secret generators, validation expression
  format, and instance/package setting persistence.
- Define the supported adapter IDs and the database object ownership contract.
- Choose the capability API 1.x Python handler loading protocol and typed
  request/result schema.
- Define setup completion invalidation rules and package-upgrade migration
  staging/recovery.
- Finalize route template parameters and instance-specific Docker network names.
- Finalize the complete removal descriptor and preservation model.
