## Context

`delete_vectors_for_document` purges every chunk whose `metadata.document_uid` matches, via `delete_by_query` with `conflicts=proceed` (the purge is idempotent and can race with a second pass on a cancelled ingestion). OpenSearch applies the deletion immediately but only exposes it to search and `count` after a refresh. `set_document_retrievable` and `set_document_name` already pass `refresh=true` to `update_by_query`; the deletion path is the one per-document write that does not.

## Goals / Non-Goals

**Goals:**

- When `delete_vectors_for_document` returns, the deleted chunks are no longer returned by search or counted.
- Keep the change a one-option edit consistent with the existing update paths.

**Non-Goals:**

- `delete_chunk` (single-chunk `delete` by id, used by the chunk-level admin action): a different API call with its own `refresh` parameter and a different caller contract; left unchanged and reported separately.
- Ingestion (`add_documents`) visibility: bulk indexing relies on the periodic refresh by design.
- Pgvector or other adapters, and any caller-side wait or polling.

## Decisions

### Refresh inside `delete_by_query`, not caller-side

Add `"refresh": "true"` to the existing `params` dict. This mirrors the update paths and keeps the visibility guarantee in the adapter, so every caller (deletion, tag-removal purge, re-vectorization, cancellation cleanup) benefits without each one knowing OpenSearch's refresh model. A caller-side wait or `wait_for` would spread backend-specific behavior across call sites and still be timing-dependent.

## Risks / Trade-offs

- [Refresh cost] `refresh=true` forces a refresh of the index's shards once the query completes: one extra segment refresh per deleted document. Deletion is not a per-turn or per-request hot path. A bulk purge of N documents costs N refreshes, the same profile the retrievability toggle already has. If mass deletion ever becomes a measured bottleneck, a batched delete with a single trailing refresh is the follow-up, not removing the guarantee.
- [Cancelled ingestion runs the purge twice] Each pass refreshes; the second pass is a no-op delete plus a cheap refresh.

## Migration Plan

Normal Knowledge Flow code update. No data migration or configuration change. Rollback restores the eventual (about one second) visibility after deletion.
