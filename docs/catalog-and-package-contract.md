# Static Catalog and Service Package Contract

This is the first distribution contract for the greenfield OpenDock
architecture. It uses static files and Cloudflare R2; it needs no catalog API,
Worker, account service, or private GitHub access from the CLI.

## Read path: direct object downloads

The OpenDock client fetches public R2 objects over HTTPS. It does not call an
OpenDock API or Worker. The difference is that the response is a static JSON or
ZIP object from R2; there is no application server doing search, authorization,
or package selection for each request. In this design, “no API” means “no
OpenDock API service,” not “no HTTP requests.”

- `update` sends an HTTPS `GET` for `catalog/v1/index.json`, validates it, and
  replaces the local environment-specific cache.
- `search` searches that local JSON cache. If no cache exists, it first fetches
  the catalog directly from R2.
- `install <service>` resolves the release from the local catalog cache, sends
  an HTTPS `GET` for the listed ZIP object, checks its size and SHA-256, then
  extracts and registers the release locally.

The package URL is derived from the configured public R2 base URL and a
catalog-relative object key. No R2 access key, GitHub token, or write
credential is present on the client. R2's CI write path is separate from this
public read path.

## Components and publication flow

```text
private OpenDock-Services --CI-only read--> validate and package
        --> calculate SHA-256 --> publish immutable package to R2
        --> generate catalog JSON --> publish catalog last
```

CI is the only component with private source access and R2 write credentials.
The CLI reads public catalog and package objects. It never clones the source
repository and receives no GitHub or R2 write credentials.

Use separate dev and prod buckets. Keep production credentials and release
workflows isolated from development. The CLI's development profile points to
the dev bucket; the normal profile uses prod. Do not mix these catalogs in one
local package registry. Proposed key layout in each bucket:

```text
catalog/v1/index.json
packages/<service-id>/<package-version>/opendock-service.zip
```

Package keys are immutable. CI uploads and verifies the package first, then
publishes the catalog that refers to it. Catalog publication is the final
visibility step. A failed release can leave an unreferenced object, but must
not publish a catalog entry for a missing object. Promote a release by an
explicit reviewed workflow; do not let dev publish credentials write prod.

## Catalog JSON

The initial catalog is one UTF-8 JSON document. `search` runs locally over its
metadata, avoiding a search service while the catalog is small. Catalog schema
version is independent of service descriptor and capability API versions.

Illustrative shape (field spelling remains open):

```json
{
  "catalog_schema_version": 1,
  "catalog_revision": "2026-11-06T00:00:00Z",
  "services": [
    {
      "service_id": "wordpress",
      "display_name": "WordPress",
      "primary_image": "wordpress:7-php8.5-apache",
      "summary": "Publish and manage a website",
      "tags": ["website", "cms"],
      "releases": [
        {
          "version": "1.0.0",
          "artifact": "packages/wordpress/1.0.0/opendock-service.zip",
          "sha256": "<64 lowercase hexadecimal characters>",
          "size_bytes": 48123,
          "descriptor_schema": {"min": 1, "max": 1},
          "capability_api": {"min": 1, "max": 1},
          "opendock": {"min": "1.0.0", "max": null},
          "supported_hosts": ["linux", "macos"],
          "released_at": "2026-11-06T00:00:00Z"
        }
      ]
    }
  ]
}
```

`primary_image` is the compact `name:tag` of the service's declared primary
Compose image. CI derives it from the descriptor's primary Compose service and
the package's `.env.default`; it omits registry and namespace path components.
`search` displays this upstream image tag and omits OpenDock package release
versions, which remain in `releases` for install and update selection.

The client validates schema, IDs, versions, artifact key, digest shape,
compatibility ranges, supported-host metadata, and size before using an entry. Artifact keys are resolved
against the configured catalog origin and must remain under `packages/`; the
catalog cannot direct the CLI to an arbitrary host. IDs are stable/lowercase
and versions use SemVer. Display metadata is untrusted text: escape terminal
output and never interpret it as a shell command, path, or executable template.
The package descriptor repeats its service ID and version; mismatches fail
installation.

## Package format and installation

Use one ZIP archive per service release. ZIP is available in the standard
tooling on Linux, macOS, and WSL2 and can be handled by Python's standard
library if the CLI remains Python. It contains an explicit allowlist of
runtime files such as the descriptor, Compose files, tracked defaults,
optional capability handler, declared commands, routing resources, docs, and
license notices. It excludes local `.env`, generated secrets, customer data,
caches, Git metadata, and files belonging to other services. CI records a
reproducible file inventory. The catalog digest covers the exact final archive
bytes.

The installer downloads to a temporary file, enforces compressed and expanded
size limits, verifies SHA-256 before extraction, rejects absolute paths,
traversal, duplicate entries, and symlink entries, extracts to staging,
validates descriptor and compatibility, then activates the release atomically.
Failure before activation leaves the current package and all site instances
unchanged. Set concrete limits before implementation.

Installation must not import or execute a capability module. Validate handler
paths and declared function names statically from package metadata/source. Load
and validate the callable only immediately before the common workflow invokes
that capability. This preserves the rule that `install` registers code but
does not run service procedures; it does not make the later handler execution
a sandbox.

## Checksum and trust policy

Use SHA-256 and verify the complete artifact before extracting files. Record
the digest and catalog revision in local install metadata. A matching checksum
proves that the package matches the catalog entry; it does **not** prove
publisher identity if an attacker replaces both package and catalog. This is
an accepted v1 limitation to avoid signing-key management and must be stated in
security documentation.

CI-only R2 writes, least-privilege credentials, protected release jobs,
immutable keys, code review, and HTTPS reduce operational risk but do not
change that cryptographic limitation. Signatures may be added later as a
versioned trust feature.

## CI release responsibilities

1. Read the service source from the private repository.
2. Validate descriptor, capability declarations, compatibility, and allowlist.
3. Build the single-service archive and calculate SHA-256.
4. Upload to an immutable versioned R2 key and verify the object.
5. Generate the environment catalog from accepted releases, including the
   primary image tag used for search display.
6. Publish catalog last.

CI must not upload local configuration or customer data. Dev and prod use
separate credentials and workflows.

## CLI behavior

- `update` fetches and validates the selected environment's catalog, then
  atomically replaces the local cache. It does not change installed packages.
- The current client caches each environment separately in the user's cache
  directory. `update` always fetches a fresh catalog. `search` and `install`
  use the cache and fetch only when it is missing; they do not yet refresh an
  old cache automatically or use HTTP validators.
- If no cache exists, `search` and `install` fetch the catalog once before
  continuing. The current client does not report cache age.
- Current `install <service>` selects the newest stable release whose declared
  host, descriptor-schema, and capability-API ranges include this client,
  downloads it, verifies checksum, validates the descriptor through the common
  catalog parser, then activates the release and registry together. A failed
  registry write rolls back the staged release. The catalog's OpenDock version
  range is syntax-checked but cannot yet be enforced because this CLI has no
  product-version source; adding that source remains follow-up work.
- Proposed `upgrade [service]` applies compatible newer package releases and
  preserves site-instance configuration and data; the command is not
  implemented yet.
- The target release selector should choose the newest stable SemVer compatible
  with the OpenDock version, capability API, and host target. The current client
  enforces capability API compatibility but does not gate installation by host
  metadata; OpenDock-version selection is deferred until the platform publishes
  its own version. Prereleases are
  excluded unless explicitly requested.
- Catalog/download failure does not damage the current cache, installed code,
  or instance state. Catalog refresh never executes package hooks.

Automatic cache age policy, HTTP conditional requests, and stale-cache status
display are follow-up work; they are not part of the current client behavior.

## First implementation slice

The OpenDock CLI now has initial `update`, `search`, and `install` commands in
`scripts/opendock_distribution.py`. They validate static catalog JSON, cache it
per environment, download only catalog-relative package keys, check archive
size and SHA-256, reject unsafe ZIP members, and stage package activation. The
local install registry records the digest without a publisher-key field.
Catalog origins are owned by the platform configuration interface. Register
`OPENDOCK_DEV_CATALOG_BASE_URL` and `OPENDOCK_PROD_CATALOG_BASE_URL` in
`config/core.toml`; local values belong in `config/core.env`, and stable public
defaults belong in `config/core.env.default`. The URL is public metadata, not a
credential. Set the dev URL in `config/core.env`, then use the development
wrapper for distribution commands:

```sh
./dev_opendock update
./dev_opendock search uptime
./dev_opendock install uptime-kuma
```

The wrapper adds `--environment dev` to `update`, `search`, and `install` and
rejects an explicit environment override. Use `./opendock update
--environment prod` to refresh the production catalog.

The dev R2 bucket and CI publisher are connected. The Uptime Kuma `0.1.0`
release was published by tag-triggered GitHub Actions. From a local OpenDock
checkout, the user confirmed `update`, `search uptime`, and `install uptime-kuma`;
the installed release was placed under `services/extensions/uptime-kuma/releases/0.1.0`.
OpenDock now discovers that release through the local registry, includes its
descriptor-declared settings in `check-config` and `setup`, and verifies that
registry service ID/version/path match the installed descriptor. In the local
checkout, `./opendock list services` listed Uptime Kuma,
`./opendock check-config uptime-kuma` returned `OK`, and
`./opendock setup uptime-kuma` completed using existing platform configuration
and package defaults. Setup started no application containers. The user later
verified on Minibuntu that infra and Uptime Kuma containers became healthy and
the public Uptime Kuma first-run database page loaded after correcting the
Tunnel origin on the separate connector host. Database selection and
provisioning are deliberately left to the user: Kuma supports SQLite,
embedded MariaDB, and external MariaDB/MySQL. OpenDock does not create a Kuma
database or account. Wizard completion and post-setup application readiness
remain unverified. Uptime Kuma declares neither a Compose healthcheck nor an
application readiness hook. The CLI still lacks the proposed 24-hour refresh
policy and `upgrade`; purge, domain-scoped instances, and multi-domain
isolation are not implemented or verified. Do not treat the first-run page as
proof of a full service lifecycle.

## Remaining implementation work

- Automatic catalog refresh policy and behavior when the catalog is offline.
- Production URL and dev-to-prod promotion workflow.
- Whether future signatures cover the catalog, artifact, or both, and how
  trusted keys would be distributed.
