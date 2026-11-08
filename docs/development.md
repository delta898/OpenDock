# Platform Development

OpenDock is the platform repository. It owns bootstrap, the shared CLI,
configuration, runtime orchestration, and the service catalog client. Service
integrations and their application-specific behavior are maintained in the
separate OpenDock-Services repository.

## Architecture contracts

The product boundary and rollout direction are documented in
[`product-distribution.md`](product-distribution.md). The detailed contracts
cover:

- [`catalog-and-package-contract.md`](catalog-and-package-contract.md): static
  catalog, package layout, integrity checks, and installation.
- [`service-contract.md`](service-contract.md): descriptors and optional
  service capabilities.
- [`command-model.md`](command-model.md): common command behavior and
  domain-scoped instances.
- [`command-architecture.md`](command-architecture.md): ownership between the
  common CLI and service-provided behavior.

These documents distinguish the agreed product direction from behavior that
has been implemented or verified. Check their status notes before relying on
a proposed capability.

## Platform changes

- Keep service-specific names and application logic out of the OpenDock CLI.
- Put platform-owned defaults in the matching `config/*.env.default` file and
  declare setting ownership in the corresponding TOML descriptor.
- Keep private effective values, credentials, and host-specific routes out of
  Git. Bootstrap and sync must preserve them.
- Resolve packages through the catalog and installed-package registry; do not
  construct package paths from service IDs.
- Keep bootstrap limited to the runtime files and host prerequisites required
  by users. Development tools, CI files, and maintainer-only utilities do not
  belong in its install allowlist.
- For destructive behavior, show the exact owned resources and require
  confirmation before changing them.

## Local workflow

Use the development wrapper to work against the development catalog:

```sh
./dev_opendock update
./dev_opendock search <words>
./dev_opendock install <service-id>
./dev_opendock launch <service-id>
```

For local CLI development, inspect the command help and the relevant contract
before changing behavior. Keep service lifecycle behavior in the common
workflow only when it applies to every service; application-specific
preparation belongs with the service integration in OpenDock-Services.

## Local service integration test

From OpenDock, run the one-command pre-push test with the service ID:

```sh
./scripts/test-service.sh <service-id>
```

By default the companion OpenDock-Services checkout is expected at
`../OpenDock-Services`; set `OPENDOCK_SERVICES_ROOT` if it is elsewhere.

The wrapper builds a local ZIP, then invokes the OpenDock test runner. The
runner creates a tracked-code-only checkout under the system temporary
directory, installs the ZIP there, uses private test configuration and unique
Compose project names, and starts infra, the service, and Caddy without reading
or publishing an R2 catalog or changing Cloudflare routes. The wrapper checks
the service hostname through Caddy on a loopback-only HTTP port, then removes
the temporary checkout, test containers, named volumes, network, and ZIP. It
prints a pass/fail result. If cleanup cannot complete, it prints the preserved
runtime path for recovery.

The lower-level runner can also be used directly when inspecting a package:

```sh
./opendock local-test start /tmp/<service-id>.zip --domain <service>.local.test
./opendock local-test status /tmp/opendock-local-tests/<id>
./opendock local-test stop /tmp/opendock-local-tests/<id>
./opendock local-test clean /tmp/opendock-local-tests/<id>
```

`clean` stops the recorded Compose projects, removes only volumes carrying
their project labels, removes the exact test network, and deletes the
disposable checkout. It does not run a service purge against the main host.
Packages that request `/var/run/docker.sock` are refused because they can
control the host Docker daemon outside those Compose namespaces. For an
explicitly trusted service on a disposable Docker host, the wrapper accepts
`--allow-host-docker-socket`; this grants the service access to that host daemon
and does not sandbox it. The wrapper verifies local ZIP installation, setup,
service start, and an HTTP response through Caddy. It does not verify
application-specific workflows, CI publication, or Cloudflare DNS/Tunnel
behavior.

Before proposing a validation result, distinguish automated checks run in the
repository from behavior verified on a real host. A passing package or CLI
check does not establish that an application completed its first-run setup or
is ready through its public route.
