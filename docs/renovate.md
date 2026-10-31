# Renovate

OpenDock uses the Mend Renovate Cloud-Hosted GitHub App to propose dependency
updates. Renovate never deploys images to the server. It creates pull requests;
review and merge them, then update the server through the normal OpenDock
workflow.

## Enable the Cloud-Hosted App

1. Merge `renovate.json` and the `renovate:` annotations in the tracked `.env`
   files into the repository's default branch.
2. Open the [Renovate GitHub App](https://github.com/apps/renovate) while signed
   in to the account or organization that owns OpenDock.
3. Install it and grant access to the OpenDock repository.
4. Renovate will scan the repository and start opening dependency update
   pull requests. Review the Dependency Dashboard issue and the first update
   pull requests.

The GitHub App installation requires repository owner or organization admin
access. No Renovate token or scheduled GitHub Actions workflow is needed for
the Cloud-Hosted App.

## What Renovate tracks

- Docker images in Compose files are handled by Renovate's built-in Docker
  Compose manager when they are literal image references.
- Most OpenDock tags are stored in `.env` files and interpolated in Compose.
  The `renovate:` comments identify the Docker image associated with each tag;
  `renovate.json` uses the regex custom manager to update those values.
- GitHub Actions references such as `actions/checkout@v4` are detected by the
  built-in GitHub Actions manager.

All image tags remain human-reviewed. Renovate automerge is disabled. Docker
tags can encode compatibility as well as a software version, for example an OS
base or language runtime. Check those changes and service release notes before
merging, especially database and stateful service image updates.

## Inspect configured versions

`./opendock info` lists each Compose image, the configured tag, and any
container state Docker reports. To show one service or project, pass its name:

```sh
./opendock info
./opendock info wordpress
./opendock info supabase
```

The configured tag comes from the repository's `.env` and shell environment.
The running column reports the image and status of containers Docker knows
about. If Docker is unavailable, the command still displays configured image
tags and reports that runtime state could not be read.
