## Why

Large metadata-rich corpus trees consume model context and can omit the document the user needs. Raising the character budget cannot reliably answer a filename lookup or "latest document added" across a large scope. Tracking: [#3055](https://github.com/ThalesGroup/fred/issues/3055).

## What Changes

- Extend `list_document_tree` with a literal case-insensitive filename/title filter, stable name/arrival sorting, a document limit and a continuation cursor.
- Select authorized document pages before hydrating metadata. Latest-known arrival uses `sort_by="added_to_kb"`, `sort_order="desc"`, `limit=1`; missing stored dates remain unknown.
- Return continuation and unknown-arrival information to the agent without leaking unauthorized documents or internal cursor details into user-visible traces.
- Preserve the existing folder hierarchy and character budget. A budget-limited page must resume before its first omitted document.
- Keep existing vector search for content discovery and legacy tree requests/results readable.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `team-resource-spaces`: Authorized corpus discovery gains bounded, filterable, sorted document pages with reliable continuation and explicit chronology limits.

## Impact

Knowledge Flow corpus-tree and metadata services, `fred-core` document stores, SDK tree contracts, runtime adapter/client, document-access tool, frontend trace parser/detail and generated Knowledge Flow API types. Update the runtime contract, component UX and an operator note; no new endpoint family or capability.

This PR targets `swift` directly. The metadata/UI work in #3053 will merge first, then this branch will be updated from `swift`; no stacked PR or duplicated implementation is included here. This change currently contains planning artifacts only.
