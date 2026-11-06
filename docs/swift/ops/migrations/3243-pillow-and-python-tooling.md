---
schema: 1
title: "Update Pillow and align Python tooling"
impact: none
configuration: none
configuration_reason: "Dependency and build-tool pins change; deployed application configuration is unchanged."
no_action_reason: "Normal image deployment applies the Pillow update; no data or API migration is required."
---
## Applicability

Fred deployments upgrading to the Pillow 13 security refresh.

## Prerequisites

No additional deployment prerequisites. Developer environments, CI and Docker
builds use uv 0.13.5. The Make bootstrap updates an existing uv installation when
its version differs from the pin. Install the same version for direct shell use.

## Configuration

No application configuration changes. Ruff explicitly retains the previous
Python file scope and lint rule selection after the tool upgrade.

## Upgrade

Deploy rebuilt images normally. Developers can run `make dev` in each Python
component to install the pinned tooling and dependencies.

## Validation

Check `uv --version` and the component's `.venv/bin/uv --version` report 0.13.5.
Run `make code-quality` and `make test` before merging the dependency refresh.

## Rollback

Use the normal image rollback procedure. Reverting Pillow can reintroduce the
vulnerabilities addressed by this update; no data migration is involved.

## Limitations

Tooling consistency does not establish application compatibility. Full tests
and image builds must validate the dependency refresh before release.
