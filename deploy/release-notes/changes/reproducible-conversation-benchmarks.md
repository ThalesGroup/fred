---
schema: 1
title: "Reproducible local conversation benchmarks and additive model source assignment"
impact: minor
configuration: local
configuration_reason: "Optional factory model values add a local mock source and workload binding; normal production chart configuration is unchanged."
covers:
  - c3f3a58ca04e9bf4040765d3f8fee4c9c69a834e
---
## Applicability

Local Swift/Weaver conversation comparisons using the shared benchmark client,
including fresh installations and repeated full deployments. The Python SDK fix
also applies to Weaver Agent Pods receiving the current resolver projection.
This note also covers the accompanying runtime Grafana dashboard update.

## Prerequisites

Use matching Git checkouts of Fred, fred-deployment-factory and the mock OpenAI
server. Follow the factory's normal infrastructure/bootstrap and demo provisioning
procedure before preparing benchmark users. Existing installations retain their data;
this change requires no reset or schema migration.

## Configuration

Follow the factory's versioned
[benchmark guide](https://github.com/fred-agent/fred-deployment-factory/blob/weaver/docs/BENCHMARKS.md).
Its optional `VALUES` file adds the mock source and local
workload binding to normal values. Operator credentials and generated account
passwords are local private inputs, never committed overlays or command-line secrets.

## Upgrade

Build and deploy the normal images from the checked-out Fred sources. The
`fred-agents` build includes `libs/fred-sdk` for both the API and worker; it accepts
the resolver's `default` and `reasoning_default_on` fields without a hotfix image.
Deploy the normal Grafana dashboard through the existing provisioning procedure.

The factory's mock values reuse `platform.organization_models`: startup and
provisioning add the source to Acme, including after initialization. Existing
permissions, defaults and receipts stay unchanged. The Owner then refreshes and
permits the model in the UI; no manual source assignment is required.

## Validation

Confirm that the source appears in the intended organization's model inventory and
that the existing policy/default choices are retained. Repeating source assignment
must leave the policy and initialization receipt unchanged. Use the
[client preparation command](../../../developer_tools/benchmarks/README.md)
to verify the dedicated test accounts before any explicitly authorized scenario.
A scenario report checks deterministic replies and persisted history; setup alone
proves no performance or full redeployment reception.

## Rollback

Redeploy the previous configuration/images through the normal procedure. Removing
an optional profile is not model-permission revocation: persisted assignments and
policies remain. If retiring the benchmark, first withdraw its model permissions
through the Owner's normal model-policy API and disable the source in platform
configuration with an increased source revision. Preserve initialization receipts.

## Limitations

The assignment command is a trusted operator CLI, not a browser API. It requires
an existing active organization and an existing source; assigning a disabled source
does not enable it. The benchmark profile is local and opt-in. This change adds no
migration from older incompatible Weaver schemas or Swift data, and does not
establish real-model performance or validate every local model-policy combination.
