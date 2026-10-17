## Why

Manager exposes document mutations and submits workflow types without a compatible worker or upload path. The user approved removing this provisional surface after audit F3; Resources needs only metadata reads.

## What Changes

- **BREAKING**: remove document creation, rename, deletion and ingestion HTTP operations and their generated client operations.
- Remove the ingestion client, its configuration and API startup connection to Temporal.
- Preserve metadata reads, folder operations, authorization, UI and the manager-owned space-deletion worker.
- Reconcile arc42 and the existing capability contract. Admission reconstruction remains a separate lot.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `fred-manager-provisioning`: expose only implemented document reads in the provisioned Resources journey; keep API startup independent of Temporal.

## Impact

Rust API/startup/configuration, OpenAPI, generated frontend client and generation helper, tests, k3d reset validation and arc42. No database migration, role/model change, content purge or UI redesign. Existing issue #3092 tracks this reconstruction work.
