## Why

The reconstruction checkout deploys Rust manager through the normal factory command, but does not activate its document storage and processing. Existing examples require manual assembly and share storage credentials, so a successful PDF demo would not establish production-representative access boundaries or explain the full persisted layout.

Tracking: [#3180](https://github.com/ThalesGroup/fred/issues/3180). This deployment acceptance slice follows the archived storage/processing implementation. The active `integrate-manager-fred-deployment` change explicitly excludes ingestion; its existing acceptance remains separate.

## What Changes

- Provide one explicit, reviewable k3d ingestion profile, selected through the factory's existing `VALUES` mechanism, with a complete operator procedure rooted at `deploy/k3d/`. Reuse the production Fred chart and existing configuration fields.
- Provision separate application storage identities and the existing worker authentication contract through instance-owned infrastructure configuration. Keep application credentials in Secrets and infrastructure administration outside application pods.
- Activate original storage, manager dispatch, KF processing, isolated vectors and an exported contract matching the deployed worker image and effective profile configuration.
- Align manager's physical storage convention with Swift: retain the configured `<bucket_name>-documents` bucket and document-local `input/` and `output/` roots, and leave the separate `<bucket_name>-objects` bucket in its existing role. `Raw` and `derived` describe content roles, not new bucket names. Preserve immutable processing generations beneath `output/`.
- Adapt manager key construction, persisted storage bindings and ownership-aware cleanup for this shared documents bucket. Preserve integrity, publication and authorization guarantees; verify provider enforcement before claiming workload isolation. Do not infer data adoption from matching bucket names.
- Document sources, processing outputs, SQL authority, vector storage and temporary files in the existing arc42 document journey, with exact inspection commands and a role/access matrix.
- Validate effective manifests, denied storage access, resource budgets, a real PDF journey and retry/restart behavior before describing the profile as validated.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `local-helm-deployment`: an explicitly selected, reproducible ingestion profile with checked prerequisites, least-privilege credentials and verifiable operator evidence.

## Impact

Fred: manager storage configuration/key construction/cleanup, affected KF artifact and maintenance consumers, `deploy/k3d/`, existing chart examples/templates/schema where necessary, focused storage/deployment tests, arc42 chapters and the existing Rust migration guide. Companion factory work: instance values, scoped object-store identities/policies, workload identity provisioning and Secret references. Unrelated runtime reconstruction is excluded.

The developer confirmed alignment with Swift naming/layout on 2026-10-21 to reduce migration work. This supersedes the proposed `fred-kb-default-raw` / `fred-kb-default-derived` split. Document APIs, UI and permission meaning remain unchanged. Existing bytes need not be copied solely to satisfy a new naming convention; importing legacy document identities, SQL state and manifests is still a separate migration design. Production uses GCS on S3NS: validate its actual interface and policies before claiming compatibility. An existing Rust SQL storage binding cannot be changed by editing YAML alone. No data migration/reset, cluster rollout, performance campaign or push is performed by preparing this proposal. The complete implementation scope and acceptance still require confirmation; the storage alignment decision itself is settled.
