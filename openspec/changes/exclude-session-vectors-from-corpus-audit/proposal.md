## Why

The platform corpus audit (`MetadataService.audit_stores`) reports every vector-store document UID without a metadata row as `orphan_vectors`. Chat attachments are stored as session-scoped vector chunks with no metadata row by design, so every valid attachment shows up as an orphan. The admin audit becomes noisy and genuine orphans get lost among false positives. Tracked by GitHub issue #3201.

## What Changes

- Before reporting `orphan_vectors`, the audit classifies each vector-only UID with the existing vector-store hook `is_session_scoped_document` (already the authority for platform-admin attachment deletion) and skips UIDs classified as session attachments.
- Classification runs off the event loop and only for vector-only UIDs; metadata-backed documents are never classified.
- When classification is unsupported or fails, the UID stays reported as `orphan_vectors` (a failure is logged), so a real orphan is never hidden.
- Audit totals (`total_seen`, `vector_count`) and every other finding kind are unchanged.

## Capabilities

### New Capabilities

- `corpus-store-audit`: How the platform corpus audit classifies vector-store data that has no metadata row.

### Modified Capabilities

None.

## Impact

- Affected code: `audit_stores` in `apps/knowledge-flow-backend/knowledge_flow_backend/features/metadata/service.py` and `tests/features/test_metadata_audit.py`.
- `fix_store_anomalies` is unaffected beyond seeing fewer orphan findings; it never acts on orphans.
- No API, schema, configuration, or vector-store adapter change. Every adapter inherits the hook from `BaseVectorStore`.
- Cost: one chunk lookup per vector-only UID during an admin-triggered audit.
