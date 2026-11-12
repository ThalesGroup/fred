## Why

Opening a wide `read_query` result blocks the trace drawer: replaying the reported response creates 19,101 DOM nodes and takes about four seconds before the SQL appears. Users also need to see how much argument and result text a tabular call contributes without confusing that size with billed model usage. Tracking: [#3527](https://github.com/ThalesGroup/fred/issues/3527), related to Epic #2738.

## What Changes

- Show recorded SQL promptly with its existing copy action and a bounded, explicitly labelled result preview.
- Avoid syntax highlighting large result JSON and bound initially rendered rows, columns and cell text.
- Add localized input/output payload token estimates beside status and duration for supported tabular tools. Estimates describe recorded arguments and returned content, not the deciding model call's usage.
- Preserve live/history parity, failure diagnostics and unknown-tool redaction.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `mcp-capabilities`: responsive inspection and payload-size estimates for supported tabular tool traces.

## Impact

Frontend trace drawer, its SQL/result presentation and trace helpers, French/English translations, regression tests and the existing trace UX documentation. Reuse recorded tool parts; no backend, API, database, model-call or billing-accounting change. Runtime-side failure handling and exhaustive workbook auditing are outside this change.
