# OpenDock Service Contribution Meta Prompt

Copy this prompt into an AI coding assistant from the root of an OpenDock
checkout. Replace the values in the input block. Use `UNKNOWN` when you do not
know an answer; do not guess. The assistant should inspect the repository and
verify product-specific details against official sources before editing.

```text
You are preparing a new Docker Compose service contribution for OpenDock.
Work in the current OpenDock repository and follow its existing architecture.

## Service inputs — fill these in

- Stable service ID (lowercase, hyphenated): {{SERVICE_ID}}
- Display name: {{DISPLAY_NAME}}
- Official project/documentation URL: {{OFFICIAL_URL}}
- Official container image(s): {{IMAGE_AND_IMAGE_SOURCE}}
- Desired version/tag or version policy: {{VERSION_OR_POLICY}}
- Main Compose service and internal web port: {{COMPOSE_SERVICE_AND_PORT}}
- Default hostname label, if it should be publicly routed: {{DEFAULT_SUBDOMAIN_OR_NONE}}
- Required user-provided settings: {{USER_SETTINGS_OR_UNKNOWN}}
- Secrets the application needs: {{SECRET_SETTINGS_OR_UNKNOWN}}
- Persistent state and bind mounts: {{PERSISTENT_DATA_OR_UNKNOWN}}
- Shared OpenDock dependencies, if known: {{DEPENDENCIES_OR_UNKNOWN}}
- Application-specific first-run, validation, secret, or post-launch work: {{SPECIAL_BEHAVIOR_OR_NONE}}
- Other constraints or intended use: {{CONSTRAINTS_OR_NONE}}

## Required workflow

1. Read `AGENTS.md`, `docs/adding-services.md`,
   `docs/command-architecture.md`, and relevant sections of
   `docs/development.md`. Treat these repository files as the OpenDock contract.
2. Inspect at least one simple existing service and, only if relevant, an
   existing service with the same dependency or capability. Inspect its
   descriptor, Compose file, defaults, Caddy snippet, README, and tests.
3. Verify image names, supported tags, required environment variables, data
   locations, ports, architecture support (Linux amd64 and arm64 where
   available), health/readiness behavior, and proxy requirements using official
   project or image documentation. Prefer primary sources. Record source links
   in the proposed service README or response. Clearly mark facts you could
   not verify.
4. Before editing, summarize the planned files, runtime data that removal would
   delete, required user inputs, uncertain assumptions, and whether any
   existing OpenDock contract is insufficient. Ask only for information that
   cannot be safely verified or reasonably defaulted. Do not make changes that
   require a new core contract until explaining the gap and a minimal proposal.
5. Add a `services/{{SERVICE_ID}}/compose.yml` and a valid adjacent
   `services/{{SERVICE_ID}}/opendock.toml`. OpenDock discovers Compose-backed
   services from this directory; do not add a hard-coded service branch to
   `opendock` or a duplicate service registry.
6. Put non-secret defaults and Renovate-tracked image tags in
   `services/{{SERVICE_ID}}/.env.default`. Use the repository's exact
   `# renovate: datasource=docker depName=<image>` annotation immediately
   above each tracked image variable. Never place actual credentials or
   generated secrets in tracked files.
7. Declare only existing platform dependencies, shared setup groups, optional
   config sections, setup field kinds, and capability API v1 capabilities.
   Do not declare a capability without a matching handler. Do not create
   placeholder handlers for ordinary Compose behavior.
8. If public routing is requested, declare the service's subdomain setting and
   Caddy handler in the descriptor, then add a
   `gateway/caddy/conf.d/{{SERVICE_ID}}.caddy` snippet that targets the
   verified Compose service and internal port. If routing is not requested,
   omit the routing metadata and explain that the service remains manageable
   without a default public hostname.
9. Declare `[removal]` ownership and preservation for every service-owned
   runtime resource. Compose named volumes are removed with the project;
   declare host paths, private config, extra images, labeled side containers,
   and shared database objects only when their ownership is proven. Explain
   destructive removal behavior in the service README.
10. Add a concise service README covering first launch, configuration, default
    URL, persistent data, updates, security notes, and removal. Do not copy
    generic Docker background into it.
11. Run appropriate static validation and the repository test suite using a
    supported Python version. At minimum check `./opendock list services`,
    `./opendock service {{SERVICE_ID}}`, and
    `./opendock check-config {{SERVICE_ID}}` after configuration is available.
    Do not run `launch`, publish external routes, delete existing data, or
    confirm a destructive removal unless the user explicitly requested that
    runtime operation.
12. Report changed files, source verification, test results, unverified
    behavior, and any contract gap. Do not claim a real deployment or removal
    was verified unless it actually was.

## Architecture and safety constraints

- The common CLI owns workflow order, configuration persistence, confirmation,
  shared infrastructure, gateway and route publication. The service owns
  application-specific knowledge and operations.
- Service capability handlers are trusted local Python code, not a sandbox.
  Keep them scoped, typed, and idempotent. Never assume a capability API that
  is not declared by the current repository.
- A service directory plus `compose.yml` and valid `opendock.toml` is the
  discovery contract, but supporting a service may also require a Caddy snippet
  or existing group metadata outside the directory. A new shared database
  group, config layer, service runtime, or unsupported capability is a platform
  change; stop and present that need instead of hiding it in the service.
- For a public Docker service, keep the cross-file mapping consistent:
  `opendock.toml` handler name == Caddy snippet name; Caddy upstream service
  name == `compose.yml` service name; Caddy upstream port == the verified
  container port; Compose service joins `shared-net`; subdomain key is declared
  in setup metadata and has a safe value in `.env.default`.
- Do not invent defaults for required credentials, port mappings, data paths,
  health checks, security settings, or license terms. If upstream documentation
  is incomplete, explain what is unknown and choose a safe, explicit result.
- Make changes only inside the current checkout. Do not commit, push, publish,
  deploy, or alter an external account.
```
