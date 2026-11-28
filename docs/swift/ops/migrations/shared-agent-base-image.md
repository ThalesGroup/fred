---
schema: 1
title: "Publish a shared Fred agent base image"
impact: none
configuration: none
configuration_reason: "The Fred agent chart and runtime configuration keep the same image reference, user, port, entrypoint, and environment variables."
no_action_reason: "The published fred-agents image now inherits a separate base containing shared system and Python dependencies. Deployments still pull only fred-agents. External agent pod maintainers can opt into the base image when rebuilding their own pods."
---
## Applicability

Fred deployments and maintainers of external agent pod images.

## Prerequisites

None for existing deployments. External pod builders need access to GHCR.

## Configuration

No deployment values change. External pods may build `FROM ghcr.io/thalesgroup/fred-agent/fred-agents-base:<version>` with the version matching their Fred release.

## Upgrade

Deploy the new `fred-agents` image normally. Its base supplies Ubuntu 24.04, Python 3.12, LibreOffice Writer and Impress, fonts, `fred-pod`, `fred-core`, `fred-sdk`, `fred-runtime`, and shared third-party Python packages. The final image installs Fred's default capabilities and application.

Every `code/v*` tag publishes both images with the same version. A `swift` push publishes only images whose inputs changed; the existing `swift-dev` base remains in use when only capabilities or the agent application change. This input-based selection also applies to the frontend and backend `swift-dev` images.

## Validation

Confirm the `fred-agents` pod starts, exposes `/fred/agents/v2`, and can render a document and presentation preview. Check the build job's image size summary and Trivy artifacts for both agent images. Trivy remains advisory; investigate critical findings before using a new digest in production.

## Rollback

Redeploy the preceding `fred-agents` image. The base is part of the final image at build time, so no separate runtime image rollout is needed.

## Limitations

The base includes LibreOffice even for pods that do not use Office capabilities, as chosen for this first shared image. External pods must still install their own capabilities and application dependencies.
