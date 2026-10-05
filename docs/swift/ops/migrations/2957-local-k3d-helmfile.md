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

Factory installation values remain in `k3d-apps/fred/values.yaml`, selected by
`FRED_VALUES` (one file). `FRED_DIR` selects the local Fred checkout. The chart comes
from that checkout; the former OCI chart/version options are no longer supported
by this local command. Model credentials remain outside Git in the existing secret.

## Upgrade

In the factory, replace `make k3d-fred` with `make k3d-app FRED_DIR=/path/to/fred`.
First run `make k3d-app-validate FRED_DIR=/path/to/fred` for non-mutating validation.
The existing release is upgraded; no cluster recreation or data migration is required.
Initial bootstrap guidance now prints a token-retrieval command instead of the token.

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
