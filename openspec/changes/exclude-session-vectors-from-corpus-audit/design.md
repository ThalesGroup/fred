## Context

`audit_stores` unions the metadata, content, and vector UID sets and flags a vector-store UID with no metadata row as `orphan_vectors`. Chat attachments ingested through `/fast/ingest` write only vector chunks whose metadata carries `scope: "session"`. `BaseVectorStore.is_session_scoped_document(uid)` already classifies a UID as an attachment when every chunk carries that marker (or no chunk remains), returns `False` when the adapter cannot fetch chunks (`NotImplementedError`), and lets a real lookup failure propagate. Ingestion deletion authorization uses it through `asyncio.to_thread`.

## Goals / Non-Goals

**Goals:**

- Stop reporting valid session attachments as `orphan_vectors`.
- Never hide a genuine corpus orphan, including when classification is unsupported or fails.
- Add no blocking call on the event loop.

**Non-Goals:**

- A batch "list session document UIDs" adapter query (see Risks).
- Changing `orphan_content`, `missing_*` findings, audit totals, or `fix_store_anomalies`.
- Reconciling vectors left behind by partial deletion (separate tracking).

## Decisions

### Reuse the existing classification hook

The audit calls `is_session_scoped_document` rather than inspecting chunk metadata itself, so the audit and deletion authorization share one definition of "session attachment". A mixed UID (any chunk without the marker) is a corpus orphan and stays reported.

### Classify only vector-only UIDs, in one worker thread

Only UIDs present in the vector store and absent from metadata are candidates. They are classified in a single `asyncio.to_thread` call that iterates sequentially, keeping the event loop free without fanning out concurrent store queries from an admin audit.

### Fail toward reporting

A candidate is skipped only when the hook returns `True`. `False`, `NotImplementedError` turned into `False` by the base hook, any exception raised by the lookup, or an adapter without the hook all keep the `orphan_vectors` finding. Exceptions are logged at warning level with the UID.

## Risks / Trade-offs

- [One chunk lookup per vector-only UID; platforms with many attachments pay N sequential round trips per audit] → Accepted: the audit is admin-triggered and already makes one chunk-count call per vector UID. A single adapter-level query for session UIDs would need a new capability across OpenSearch, pgvector, ClickHouse, and Chroma and is deferred until volumes justify it.
- [A UID whose chunks vanish between listing and classification reads as session-scoped (no chunks) and is not reported] → Accepted: nothing remains in the vector store to orphan; the next audit reflects the store as it is.
- [Classification correctness depends on adapters persisting the `scope` chunk metadata] → Same dependency as deletion authorization; unit tests cover the service logic only, not each adapter.

## Migration Plan

Normal Knowledge Flow code update; no data migration or configuration change. Rollback restores the false positives.
