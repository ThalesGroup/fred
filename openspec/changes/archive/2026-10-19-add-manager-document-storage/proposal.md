## Why

Resources can manage manager folders, but cannot store or retrieve their original
documents. Reconstruct the first complete document journey in Rust: import an
original into a folder, find it after a reload, and individually download the same
bytes.

This is a bounded follow-on to
[`simplify-corpus-authorization`](../simplify-corpus-authorization/design.md),
not implementation of that change's conversation, search or evaluation work.
Tracking: [#3172](https://github.com/ThalesGroup/fred/issues/3172).
Related: [#2938](https://github.com/ThalesGroup/fred/issues/2938) and
the manager foundation [#3092](https://github.com/ThalesGroup/fred/issues/3092).

## What Changes

- Give manager ownership of original bytes in S3-compatible storage, document
  metadata, storage admission, and durable receipts for these uploads. Keep
  direct roles and space hierarchy canonical in OpenFGA.
- Connect the existing Resources page, upload drawer, import panel, directory
  table and download control to these contracts. Preserve their routes, layout,
  navigation, controls and styles. A stored original is explicitly not indexed.
- Make upload creation idempotent, bounded and safe across concurrent requests,
  revoked access, ambiguous storage acknowledgments and process restarts.
  Include autonomous cleanup of unsuccessful uploads, without Temporal.
- Use **creation only**, confirmed by the developer for this first lot: an
  existing name produces a conflict, never an implicit overwrite. Replacement
  remains a separate lot.
- **BREAKING**: define manager contracts for space/folder/document identities.
  Do not emulate knowledge-flow tags, document UIDs, NDJSON ingestion messages
  or Swift storage paths. No compatibility shim or migration job belongs here.
- Reconcile the import acceptance specifications with the distinction between
  storing an original and processing it. This does not change Python ingestion.

No ingestion submission, Temporal call, extraction, embedding, search, preview,
document rename/move/deletion, bulk/recursive ZIP download, general task-service
migration, or documentation tooling redesign is included. Existing folder operations remain supported;
pending and stored documents must prevent destructive folder/space deletion.

## Capabilities

### New Capabilities

- `document-storage`: authorized, durable original upload, browsing, download,
  storage admission and recovery in manager.

### Modified Capabilities

- `document-import-conflicts`: distinguish manager's creation-only conflict
  behavior from the existing knowledge-flow replacement workflow.
- `document-import-experience`: distinguish a stored original from processed
  knowledge while preserving navigation, progress, retry and interruption UX.

## Impact

`apps/control-plane`: document service/API, PostgreSQL migration, S3 SDK, typed
configuration, lifecycle coordination, storage reconciliation and tests.
`apps/frontend`: generated manager client and existing Resources/import consumers.
The current control-plane deployment contract must carry the new content-store
configuration and bounded temporary storage without replacing the integration
already on this branch. The S3 acceptance target includes deployed SeaweedFS 4.29.

After implementation and independent review, update arc42 chapters 02, 03,
03a, 05, 08, 09 and annexes A1-A3 in the same commit. Plans remain here;
the compiled-OpenAPI/rustdoc/test-example/CI documentation ideas are separate.
