## Why

`list_document_tree` labels the file's creation date as its upload date and discards the time. The agent needs arrival chronology and useful descriptive metadata, while the tool detail panel needs a compact presentation as the payload grows.

Tracking: [GitHub issue #3052](https://github.com/ThalesGroup/fred/issues/3052). Publication approved by the developer on 2026-10-12.

## What Changes

- Expose explicitly labeled arrival, creation and modification timestamps, title, format/MIME, language, page/row counts, labels and source on authorized document leaves.
- Use stored `source.date_added_to_kb` for arrival chronology. Preserve full ISO 8601 timestamps and distinguish arrival from ingestion completion. Unknown dates remain unknown.
- Carry compact JSON document records as leaves in the existing indented tree string, preserving scope, whole-item pruning and the tree budget.
- Surface truncation explicitly to both ReAct and Graph agents.
- Replace the tool detail text block with folder groups and expandable document rows: name, format and arrival visible; remaining metadata on expansion; at most one document expanded.
- Mark the most recent displayed known arrival and warn when the listing is incomplete. Keep older text tree results readable without showing internal ids.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `team-resource-spaces`: useful document metadata and compact tree result presentation in the chat tool detail panel.

## Impact

- Knowledge Flow: corpus tree service/renderer and focused tests.
- Document access capability: tool description/result handling and focused tests.
- Frontend: trace parser, document tree detail component, translations and focused tests.
- Docs: runtime execution contract, component UX and one operator migration note.
- Existing API and SDK request/response shapes remain unchanged; no database migration or generated schema change is expected.
- Work is isolated on `feat/document-tree-tool-details` in `/tmp/fred-document-tree-metadata`.
