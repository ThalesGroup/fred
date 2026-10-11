---
schema: 1
title: "Keep the Python images' dependency layers cached across local and library changes"
impact: none
configuration: none
configuration_reason: "Only the Dockerfiles, the root .dockerignore and the make prod target's optional flags change; no configuration key, chart value or default changes."
no_action_reason: "The images install the same packages from the same locks, at the same paths, and start the same way; only the layer order and what enters the build context change."
---
## Applicability

Existing Fred deployments upgrading to this release, and anyone building the
Knowledge Flow, Fred Agents or Control Plane images.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required. The
Dockerfiles use only standard instructions: BuildKit and Kaniko builds work
unchanged.

## Validation

Build an image twice, changing a Python file of `libs/fred-core` in between: the
second build reuses the third-party dependency layer and, for Knowledge Flow, the
model download layers, and reinstalls only the local packages.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

A change to an application's `uv.lock` or to a local package's `pyproject.toml`
still rebuilds that image's dependency layer, as it must.
