# OpenDock Command and Instance Model

This proposes a user-facing command model for the greenfield CLI. Existing
repository commands provide operational lessons but are not a compatibility
contract.

The implemented distribution slice currently uses direct HTTPS GETs to public
R2 objects: `update` fetches static catalog JSON, `search` searches the local
cache (fetching only when absent), and `install` downloads the catalog-listed
ZIP and verifies its SHA-256. There is no OpenDock API service in this path.
Installed packages now enter the common `launch <service>` route: OpenDock
checks configuration, starts declared shared prerequisites, prepares the
service, waits for Compose's running/healthy condition, then applies gateway
and Cloudflare publication. The user verified on Linux that the service and
declared infra reached Compose healthy/running state and Uptime Kuma's public
first-run database page loaded. This is a first-launch smoke check, not the
full domain-scoped site-instance model below; database wizard completion and
application-level readiness remain unverified. Kuma's database choice and
provisioning are user-owned.

## Command layers

| Layer | Purpose | Example |
| --- | --- | --- |
| Host bootstrap | Install/check supported OS prerequisites | `opendock bootstrap` |
| Platform setup | Configure OpenDock-wide settings and shared runtime | `opendock setup` |
| Package lifecycle | Find, install, refresh, or upgrade service definitions | `search`, `install`, `update`, `upgrade` |
| Site-instance lifecycle | Configure and operate one deployment | `setup`, `launch`, `up`, `stop`, `purge` |

The same verb may have a platform and service form: `opendock setup` configures
platform-owned settings; `opendock setup wordpress --domain a.com` configures one
WordPress instance. Help must make the target and scope explicit.

## Proposed grammar

```text
opendock bootstrap [--check]
opendock setup
opendock search <terms...>
opendock list [<service>]
opendock info <service>
opendock update
opendock install <service>
opendock upgrade [<service>]
opendock setup <service> --domain <domain>
opendock launch <service> --domain <domain>
opendock up <service> --domain <domain>
opendock down <service> --domain <domain>
opendock start <service> --domain <domain>
opendock stop <service> --domain <domain>
opendock restart <service> --domain <domain>
opendock purge <service> --domain <domain>
opendock uninstall <service>
opendock site list
opendock site show <instance-id>
opendock domain list
opendock domain add <domain>
opendock domain rename <old-domain> <new-domain>
opendock domain remove <domain>
```

`list` shows installed service packages (optionally narrowed to one package);
`site list` shows configured instances. `search` searches the catalog. `info`
shows package metadata and installed version. A no-target `launch` does not
mean “launch everything”; it requires a service and an instance.

## Verb meanings

| Command | Meaning | Relationship |
| --- | --- | --- |
| `bootstrap` | Check/install host-level prerequisites | Platform-only |
| `setup` | Collect/persist platform or instance configuration | Not a runtime command |
| `search` | Search cached static catalog | Read-only |
| `update` | Refresh local catalog cache | Does not change installed packages |
| `install` | Install a service package definition/release | `uninstall` |
| `upgrade` | Apply a newer compatible package release | Preserves site instances |
| `launch` | Prepare if needed, start and publish one site if configured | Compound workflow |
| `up` / `down` | Create/start or remove containers for one site | Down preserves data |
| `start` / `stop` | Start or stop existing runtime | Runtime-state pair |
| `restart` | Restart selected instance | Runtime operation |
| `purge` | Confirm and remove one instance's owned resources/data/config/routes | Destructive; package remains |
| `uninstall` | Remove package code when no instances remain | `install` counterpart |

**Target policy, not implemented yet:** for Homebrew-like convenience,
`install` and `upgrade` should refresh the catalog automatically when no cache
exists or it is older than 24 hours; `update` forces an explicit refresh.
`search` can use a stale cache and show its last refresh time. This is client
policy, not service metadata.

Omit the ambiguous verb `remove`. `purge` is instance cleanup; `uninstall` is
package-code removal. Neither may guess resource ownership. `update` and
`upgrade` are intentionally different: refresh catalog metadata versus apply a
package version.

## Compound launch

`launch <service> --domain <domain>` is the zero-config path for an already
installed package:

1. Resolve the package and the `(service, registered domain)` instance. If
   needed, create/configure that instance using declared setup fields.
2. Generate missing machine-owned secrets and prepare safe defaults.
3. Validate platform and instance configuration. Invalid required values stop
   before runtime state changes.
4. Run an incomplete declared setup hook, starting only its required shared
   prerequisites, then run optional idempotent `prepare`.
5. Resolve runtime environment, start the selected Compose project, and wait
   for Compose's running/healthy condition. A service without a healthcheck is
   only confirmed running; application-level readiness requires a declared
   readiness capability.
6. Run optional `post_launch`, then optional application `readiness`.
7. Apply the instance route and publish external tunnel/DNS changes.
8. Report publication failures clearly; Cloudflare setup is required.

**Current implementation note:** the package launch path uses `docker compose
up -d --wait --wait-timeout 180` for the selected service and required shared
infrastructure. It validates configuration and declared capabilities before
starting those projects. Gateway startup uses the same Compose wait. Public
launch requires Cloudflare settings before changing service or route state;
external API failures during publication are reported as failures. Uptime
Kuma's package does not declare a Compose healthcheck or application readiness
hook, so Compose wait alone does not confirm its HTTP UI is ready. The user
verified the first-run database page in the real environment.

When a host-local `domains.conf` exists, `launch` adds missing default routes
for the selected services in one validated write after setup and preparation
complete. A cancelled setup therefore does not leave behind a newly added
default route.

The compound command composes common unit operations; it does not duplicate
their implementation. It never installs or upgrades code implicitly. A missing
package points the user to `search` and `install`. In non-interactive mode,
missing required user choices must fail before changing service state.

`setup <service> --domain <domain>` is the configuration review/change path and
covers the same required preparation prerequisites as launch. It must not
repeat a completed interactive first-run wizard when the user only wants to
review managed settings. If the registered domain has no instance of that
service yet, setup creates an instance record and configures it; it does not
start the application runtime unless a declared service setup hook requires a
shared prerequisite. Required values are validated before the new instance is
committed; canceling setup does not leave a partial draft instance. The domain
must first exist in the platform registry, added through `domain add`.

## Multi-domain instance model

One package can have many independent instances:

```text
installed package: wordpress 1.2.0
  instance site-01 → a.com → own config/data/containers
  instance site-02 → b.com → own config/data/containers
```

Every supported service may have instances on domain A and B. Several different
services may also attach instances to the same registered base domain, with
their own derived hostnames. Instances must not accidentally share Compose
project names, secrets, database objects, persistent volumes, or purge scope.
OpenDock owns the base-domain registry and route-conflict checks. V1 allows at
most one instance of a given service per base domain. Aliases to one instance
are a separate later feature.

Use `--domain` with the service target to select/create that service's
instance for a registered base domain. This composite target is unambiguous
even when several services use the same domain. The platform stores a stable
instance ID separately. `site show <instance-id>` inspects one instance;
`site list` can filter by domain. `domain rename` previews affected service
hostnames and checks for conflicts before changing the shared record.
`domain remove` refuses while any instance still refers to it.

## State and destructive operations

- Package install/upgrade does not start containers or delete site data.
- `up` validates configuration, completes declared setup/preparation, starts
  required prerequisites and the selected Compose project, then checks health.
  It does not publish external DNS/tunnel state; `launch` composes `up` with
  route publication.
- `down` removes containers but preserves package, configuration, routes, and
  persistent data. Its public hostname remains configured but unavailable
  until the instance is launched again. `purge` removes the instance route and
  owned data; it keeps the shared base-domain record.
- `stop` stops runtime and preserves containers/data.
- `purge` shows exact instance-owned resources and requires interactive
  confirmation before destructive changes. Shared runtime and other instances
  are never in scope.
- `uninstall` refuses while any instance uses the package; purge instances
  explicitly first.
- Package activation should be recoverable: keep the prior version until the
  new release passes validation.

The common CLI owns target resolution, shared prerequisites, configuration,
Compose invocation, route publication, confirmation, and common errors.
Services own app-specific setup, readiness, migrations, and exact cleanup
declarations.

## OS rollout

1. **Linux first:** define supported distributions/versions, Docker/Compose
   prerequisites, privilege requirements, networking notes, and a clean-host
   bootstrap acceptance path.
2. **macOS second:** define runtime expectations, filesystem mount behavior,
   startup, networking, and bind-mount validation on a real supported Mac.
3. **Windows via WSL2 later:** decide supported WSL distributions, Docker
   integration, filesystem placement, networking, and Windows/Linux path
   boundaries. Until bootstrap is reliable, provide a detailed guide.

Do not claim OS support from syntax checks alone. Validate a clean host through
bootstrap, platform setup, package install, launch/repeat launch, partial
publication reporting, and purge without affecting unrelated state.

## Decisions still open

- Whether aliases are supported in v1.
- How upgrades recover when application/database migrations are irreversible.
- Exact `info` detail.
- Supported Linux distributions and macOS versions.
