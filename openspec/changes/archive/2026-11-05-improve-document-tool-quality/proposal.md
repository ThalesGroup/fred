## Why

The local November 3 audit found 11 failed document references and one NUL-containing write whose session had no durable history. The developer confirmed the illustrated parameter-guidance and controlled-rejection approach and requested implementation and before/after verification in issue #3477; API-test HTTP 401 failures are excluded.

## What Changes

- Put exact-UID guidance in the model-facing read and summary parameter schemas and clarify discovery versus reading and summarization, preserving argument names and scope enforcement.
- Reject NUL in writable-document title/content before accessing storage with a non-empty, actionable tool error; preserve existing documents.
- Persist invalid history text using an explicit diagnostic notation and transformation attribution, without altering in-flight tool arguments or losing call/result pairing.
- Compare deterministic audit reproductions and focused regressions against swift; report real-model evidence separately.

## Capabilities

### New Capabilities

- `document-tool-reliability`: Native document-reference guidance and recoverable document-write failures with durable diagnostic history. Existing MCP and Team Resources specifications cover transport/catalogs and corpus browsing, not these native writing and parameter contracts.

### Modified Capabilities

None.

## Impact

Native document access/reading/writing capabilities and the shared history serialization boundary in fred-core. No HTTP schema, database schema, new table, permission, UID format, filename resolution, retry loop, or document-content cleanup is introduced. One linear text validation/serialization pass replaces no remote operation and adds no cross-pod state.
