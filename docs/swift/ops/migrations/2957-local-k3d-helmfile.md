---
schema: 1
title: "Deploy local k3d Fred with Helmfile"
impact: minor
configuration: local
configuration_reason: "Only the local k3d workflow changes; production chart values, schemas and runtime configuration are unchanged."
---
## Applicability

Developers using fred-deployment-factory to build and deploy Fred on local k3d.
Other deployments use their normal procedure.

## Prerequisites

Use matching Fred and deployment-factory checkouts with the Helmfile workflow.
Install Helmfile from its official release with checksum verification; the tested
versions are Helmfile 1.8.1 and Helm 3.21.2. Keep the existing k3d cluster and volumes.

## Configuration

Fred's k3d installation now lives in this repository, in `deploy/k3d/`:
`helmfile.yaml.gotmpl` (the `fred-app` release), `values.yaml` (moved from the factory's
`k3d-apps/fred/values.yaml`, unchanged), and the `build`, `prepare` and `finish` hooks the
factory runs. The chart comes from this checkout; the former `FRED_CHART`,
`FRED_CHART_VERSION`, `FRED_VALUES` and `FRED_DIR` options are gone. Extra values files go
in the factory's `VALUES`. Model credentials remain outside Git in the existing secret.

## Upgrade

In the factory, replace `make k3d-fred FRED_DIR=/path/to/fred` with
`make k3d-app DIR=/path/to/fred`, and `make k3d-evaluator` with
`make k3d-app DIR=/path/to/fred-agent-evaluator`. `make k3d-app-validate DIR=...` checks
without building or changing the cluster. A local edit to the factory's
`k3d-apps/fred/values.yaml` moves to `deploy/k3d/values.yaml` here. The existing release
is upgraded; no cluster recreation or data migration is required. Initial bootstrap
guidance now prints a token-retrieval command instead of the token.

## Validation

Confirm validation succeeds, then all six Fred deployments become ready. Verify
each worker uses its backend's image, Fred opens at the configured local URL and
Grafana has Fred's dashboards. Rerunning the deploy must preserve data and keep
unchanged image content on the same tags.

## Rollback

Restore the previous Fred and factory code together. If application rollback is
needed, use the previous known deployed Fred Helm revision. Do not uninstall the
infrastructure or delete persistent volumes.

## Limitations

This change covers Fred on local k3d only. It does not migrate Maxwell, evaluator,
infrastructure lifecycle or other environments. Existing-cluster testing does not
establish installation on an empty cluster.
