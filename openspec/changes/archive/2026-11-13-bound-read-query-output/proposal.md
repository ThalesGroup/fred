# Proposal

## Why

Wide SQL result rows can exhaust the model context even under the existing row cap. Users need useful larger previews with explicit, trustworthy explanations of omitted data.

## What Changes

- Default omitted `max_rows` to a deployment-configurable 500 rows.
- Remove the fixed server row ceiling. Accept any positive row limit; explicit JSON `null` disables the tool-added row limit while retaining SQL-authored LIMIT clauses and execution guardrails.
- Bound serialized row data to a deployment-configurable 50,000 characters, retaining an ordered prefix of complete rows.
- Produce tool-owned success messages after row data for character truncation and reached row limits; distinguish known complete results from potentially incomplete results.
- **BREAKING**: explicit `max_rows: null` no longer selects the default. Retire the old deployment `max_rows` ceiling with migration guidance.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `tabular-query-safety`: configurable character-bounded SQL results, optional row limits and accurate partial-result messages.

## Impact

Knowledge Flow request/response models, query worker and serialization, MCP descriptions, packaged tabular guidance, Helm values and generated schemas, generated API clients, and supported chat trace consumers. No new storage or dependencies. Read results incrementally rather than materializing unlimited DataFrames. Preserve authorization, engine memory/time budgets and multi-pod independence.

Tracking: #3537, linked to context-management Epic #2833. The developer requested implementation on the existing `fix-tabular-trace-details` branch.
