---
schema: 1
title: "k3d deployment moves to fred-deployment-factory; self-sufficient migration hook"
impact: none
configuration: local
configuration_reason: "Only local development configuration moves: deploy/local/k3d (values-local.yaml, values-bench.yaml) and the root Makefile's k3d targets are removed, fred-deployment-factory now holds the k3d instance values. The chart's values.yaml changes a comment only; its schema gains the optional applications.<app>.migration.extraEnvVars, with no default, so existing overlays render unchanged."
no_action_reason: "No application code or configuration schema changes. The migration hook template renders only with migration.enabled (off by default) and now needs nothing but the database coordinates; the frontend image runs as uid 101, the same nginx user as before."
---
## Applicability

Deployments that enable a migration Job (`applications.<app>.migration.enabled: true`), and developers who deployed Fred on k3d with this repository's `make k3d-deploy`.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure. For k3d, a checkout of fred-deployment-factory next to this repository.

## Configuration

No configuration changes are required. The migration Job reads its database password from `dotenv.FRED_POSTGRES_PASSWORD`, as before, or from the new optional `migration.extraEnvVars` (e.g. a `secretKeyRef` to a Secret that exists before the release). The Job no longer inherits the application's `env`, `envFrom` or volumes.

## Upgrade

Deploy Fred normally. On k3d, deploy from fred-deployment-factory: `make k3d-up`, then `make k3d-fred FRED_DIR=<this checkout>`; the walkthrough is its `docs/LOCAL-DEVELOPMENT.md`, "k3d: the full stack in Kubernetes".

## Validation

Render the chart with `migration.enabled: true`: the migration Job carries `DATABASE_URL` and mounts none of the application's ConfigMaps or Secret; with `dotenv.FRED_POSTGRES_PASSWORD` set, the `<app>-migration-db` hook Secret has the `hook-succeeded` and `hook-failed` delete policies. A first `helm install` on an empty namespace completes its migration Jobs.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

A setting the migration Job used to inherit from the application's `env` or `envFrom`, other than the database password, must now be given through `migration.extraEnvVars`.
