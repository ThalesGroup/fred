---
schema: 1
title: "Isolate Weaver OpenSearch indexes in local k3d"
impact: minor
configuration: local
configuration_reason: "The k3d overlay selects Weaver-specific document, log and KPI indexes and provisions a scoped agent runtime identity. Production chart settings are unchanged."
---
## Applicability

Local Weaver deployments using the k3d hooks and fred-deployment-factory.
Swift may share the OpenSearch server, but must use separate indexes.

## Prerequisites

Use matching checkout hooks and factory commands. Preserve any local data needed
before recreating a deployment. This change does not authorize or perform a wipe.

## Configuration

Weaver selects `document-vectors`, `weaver-app-logs` and `weaver-kpi`. Ensure Swift
does not target these names. The hooks provision the `fred-agents` OpenSearch
identity with access to its observability indexes, and supply the corresponding
`agents-opensearch-password` key from the existing local application secret.
Apply the username, secret reference and provisioning hooks together.

## Upgrade

From the matching factory, prepare with `make k3d-up`, render with `make k3d-app-validate FRED=weaver APP=fred DIR=<checkout>`,
then deploy with `make k3d-app FRED=weaver APP=fred DIR=<checkout>`. Normal preparation provisions the required identities.
Existing data in formerly shared indexes is not copied or migrated automatically.
Do not delete shared indexes as an incidental upgrade step.

## Validation

After deployment, verify the rendered index names and workload identities; ingest
a Weaver document and run a conversation. Verify document, log and KPI writes go
to the Weaver indexes and that Swift still uses its own indexes. These deployment
checks remain to be performed; source inspection alone does not certify them.

## Rollback

Restore the matching previous hooks, overlay and factory configuration together.
Preserve both sets of indexes until the desired data recovery or migration has
been explicitly decided. Reverting configuration does not move indexed data.

## Limitations

This isolates local OpenSearch projections; it does not migrate Swift application
data to Weaver. A shared S3 bucket and login service remain separate concerns.
