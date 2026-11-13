# Migration guide - v3.11.1

Upgrade from: `code/v3.11.0`
Operational impact: **none** (minimum version: `3.11.1`).

Review these procedures together in the listed dependency order before deployment. Customer-specific values remain in their private repositories; Fred chart values are the production reference. Configuration files named configuration_prod.yaml are for local development only.

No-operation declarations describe ordinary deployment only. Conditional activation steps still require preparation. Validate combined upgrade and rollback in staging before production.

## Restore Docker release publication with provenance and SBOM reports

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.11.1/docs/swift/ops/migrations/docker-release-oci-export.md)

The fix restores image publication; deployed services and database schemas are unchanged.

See the source note for applicability, validation and rollback.

## Configure TLS for DuckDB HTTP Parquet reads

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.11.1/docs/swift/ops/migrations/duckdb-httpfs-tls.md)

Existing deployments upgrade normally because both new settings default to null. To activate private-CA reads, mount a CA bundle in the Knowledge Flow API, set duckdb_ca_cert_file and duckdb_enable_server_cert_verification in the chart values, then restart the API.

See the source note for applicability, validation and rollback.

## Keep successful PPT platform template uploads from showing a false error

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.11.1/docs/swift/ops/migrations/ppt-platform-upload-feedback.md)

The server already saves successful uploads; the frontend fix takes effect with a normal deployment and requires no data migration.

See the source note for applicability, validation and rollback.

## Prepare Fred release inputs and Python publication checks

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.11.1/docs/swift/ops/migrations/release-preparation-v3.11.1.md)

The release inputs and publication checks do not change application behavior or data; the in-range change notes cover upgrade actions.

See the source note for applicability, validation and rollback.

## Keep the Docker provenance fix within the existing release workflow

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.11.1/docs/swift/ops/migrations/remove-docker-release-recovery.md)

The manual recovery path is removed while OCI export and maximum provenance remain; deployments need no changes.

See the source note for applicability, validation and rollback.
