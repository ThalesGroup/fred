---
schema: 1
title: "k3d deployment moves to fred-deployment-factory; self-sufficient migration hook"
impact: minor
configuration: production
configuration_reason: "Enabled chart migration Jobs no longer inherit the application env, envFrom or volumes. Production overlays that supplied the database password or other migration inputs through those fields must use migration.extraEnvVars or dotenv.FRED_POSTGRES_PASSWORD before upgrading; bundled values need no edit."
---
## Applicability

Deployments that enable a migration Job (`applications.<app>.migration.enabled: true`), and developers who deployed Fred on k3d with this repository's `make k3d-deploy`.

## Prerequisites

Before upgrading an enabled migration Job, inspect how it receives FRED_POSTGRES_PASSWORD and any other required environment values. A Secret referenced by migration.extraEnvVars must exist before the Helm pre-upgrade hook. For k3d, have a checkout of fred-deployment-factory next to this repository.

## Configuration

The bundled chart values need no change. If a migration Job relied on the application's `env` or `envFrom`, put its required variables in `applications.<app>.migration.extraEnvVars` before upgrading. Supply `FRED_POSTGRES_PASSWORD` there when it is not in `dotenv.FRED_POSTGRES_PASSWORD`; any referenced Secret must already exist. The Job no longer inherits application volumes; review custom migration commands that expected those mounts.

## Upgrade

Apply any needed migration Job value changes before the chart upgrade, then deploy Fred. Deployments with disabled migration Jobs, or Jobs that already have all required inputs through `dotenv.FRED_POSTGRES_PASSWORD` and chart values, need no extra configuration. On k3d, deploy from fred-deployment-factory: `make k3d-up`, then `make k3d-fred FRED_DIR=<this checkout>`; the walkthrough is its `docs/LOCAL-DEVELOPMENT.md`, "k3d: the full stack in Kubernetes".

## Validation

Render the chart with `migration.enabled: true`: the Job carries `DATABASE_URL` and any configured `migration.extraEnvVars`, without application ConfigMap or Secret mounts. With `dotenv.FRED_POSTGRES_PASSWORD` set, the `<app>-migration-db` hook Secret has the `hook-succeeded` and `hook-failed` delete policies. Confirm the pre-upgrade Job completes before application rollout.

## Rollback

Restore the previous chart and its previous migration Job values if this chart change must be rolled back. Follow the separate database migration rollback guidance for this release.

## Limitations

Migration Jobs cannot use application ConfigMaps or Secret mounts that Helm creates after pre-upgrade hooks. Custom migration commands needing additional environment or files require a pre-existing source that the Job can access.
