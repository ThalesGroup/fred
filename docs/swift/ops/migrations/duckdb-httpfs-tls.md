---
schema: 1
title: "Configure TLS for DuckDB HTTP Parquet reads"
impact: none
configuration: production
no_action_reason: "Existing deployments upgrade normally because both new settings default to null; activating a private CA is optional and requires deployment-specific configuration."
configuration_reason: "Adds optional Knowledge Flow DuckDB CA bundle and server certificate verification settings to the production chart values."
---

## Applicability

Knowledge Flow deployments that read tabular Parquet artifacts from an HTTPS object store.

## Prerequisites

No additional prerequisites are required for a normal upgrade. To activate private-CA support, mount a readable CA bundle inside each Knowledge Flow API container. Existing Python and curl CA settings do not configure DuckDB `httpfs`.

## Configuration

No configuration change is required to keep existing behavior. To activate private-CA support, set `storage.tabular_store.query.duckdb_ca_cert_file` to the container path of the CA bundle and `storage.tabular_store.query.duckdb_enable_server_cert_verification` to `true`. In the Fred Helm chart, add a Secret volume through `applications.knowledge-flow-backend.extraVolumes` and `extraVolumeMounts`; see `deploy/charts/fred/README.md` for an example. Both DuckDB fields are optional. Omitted or `null` values retain DuckDB's installed defaults.

## Upgrade

Deploy Fred normally; no additional action is required for existing deployments. To activate certificate verification for tabular reads, mount the CA bundle, set both options, and restart the Knowledge Flow API. The worker can use the same config and mount for consistency.

## Validation

Run `describe_tabular_documents` and `read_query` for an existing Excel document backed by an HTTPS Parquet object. Confirm both succeed with certificate verification enabled.

## Rollback

Set both options to `null` and restart Knowledge Flow, or roll back the release. No data migration is involved.

## Limitations

These options only affect DuckDB `httpfs`; they do not change object-store URL signing, proxy routing, or TLS settings for the Python S3 client.
