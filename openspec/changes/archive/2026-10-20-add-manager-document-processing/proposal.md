## Why

Manager can store and download originals, but its Resources journey stops before
extraction and indexing. Let users process a document in its manager folder through
the existing Knowledge Flow Temporal workers while keeping identity and authority
in manager.

Tracking: [#3180](https://github.com/ThalesGroup/fred/issues/3180), following original
storage [#3172](https://github.com/ThalesGroup/fred/issues/3172), on `chore/rust-rebac`.

## What Changes

- Restore the existing upload-and-process action and fast/medium/rich selection.
  Manager atomically records processing intent when publishing the original and
  dispatches directly to Temporal, without the Knowledge Flow HTTP API.
- Run extraction and the configured output pipeline (chunking/embeddings for text,
  the existing tabular pipeline for tables) on Knowledge Flow workers. Reuse their
  processors and queue isolation; replace their catalog/storage/auth boundary for
  manager-owned work.
- Keep one manager document UUID and immutable original. Add durable processing
  attempts, bounded recovery, authorized result publication and explicit retries
  without re-upload. Expose persisted stages, failure details and processed output
  through the existing Resources/import/preview surfaces.
- Authenticate workers as workloads and bind every access to accepted manager
  work. Do not create legacy tags, document grants or a second document catalog.
- Preserve upload-only behavior and downloads during processing outages. Separate
  stored-original success from processing success; do not claim search/chat support.
- **BREAKING (reconstruction deployment only):** evolve the manager baseline schema
  in place and reset the local manager installation as the branch requires. Update
  worker configuration, service identity provisioning and deployment contracts.

## Capabilities

### New Capabilities

None. Extend the existing document lifecycle capability.

### Modified Capabilities

- `document-storage`: optional processing admission, Temporal delivery, scoped worker
  access, result publication, retries and truthful processing UI alongside storage.

## Impact

`apps/fred-manager` document routes/models/storage, scheduler and schema;
`apps/knowledge-flow-backend` activity dependencies and processor persistence seams, preserving ProcessPush and PipelineDefinition/FileToProcess unchanged;
generated frontend clients and existing Resources/import/preview bindings;
factory identities, Fred chart configuration/schemas and local configuration;
arc42 document/security/runtime/operations/quality chapters and branch migration note.

The active `simplify-corpus-authorization` change remains the broader retrieval/chat
migration. `isolate-ingestion-extraction-queues` already owns Python queue behavior;
reuse it. The external-provider design in #2240 is not implemented by this lot.
The active manager hardening and one-check proposals are not prerequisites or
permission to expand this scope; authorization budgets use the actual current code.

## Non-goals

No search/chat migration, corpus-wide backfill, connectors, external-provider SDK,
new processing algorithm, replacement, document deletion, bulk download, or user
cancellation of an accepted ingestion. Keep existing business pages and styling.
Implementation and commits stay local until explicit push approval.
