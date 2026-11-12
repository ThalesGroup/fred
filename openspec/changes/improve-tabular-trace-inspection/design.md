## Context

See proposal.md for motivation and #3527 for the diagnosis. `TraceDetailDrawer.SqlToolDetail` formats SQL and syntax-highlights pretty JSON for the first 50 returned rows. The captured result is present and valid; limiting the fixture to those same 50 rows still reproduces the stall. Replacing only the JSON highlighter with plain text reduces the drawer test from about four seconds to 170 ms. This measures the React/DOM rendering seam, not browser paint latency; the reported temporary blank state still needs browser verification.

The existing tabular search detail already bounds row, column and cell previews. `CodeBlock` has copy support. Recorded tool parts contain arguments, result content and latency, but no per-tool token accounting. The runtime execution contract section 8.57 explains why the deciding model call's usage must not be displayed as tool usage.

## Goals / Non-Goals

Keep work proportional to a bounded preview and preserve the ability to copy the recorded SQL/result. Show payload-size estimates using current history. Do not add a tokenizer service, model call, telemetry pipeline, persisted state or provider-billing attribution. Full-workbook audit coverage is unrelated to opening a trace.

## Decisions

1. **Bound the SQL result view.** Render the query first. Reuse the existing tabular preview bounds (five rows, eight columns, 160 characters per cell and bounded field names) and explicitly show returned versus previewed data. Render response JSON without syntax highlighting. Keep the full returned response available through an explicit copy action rather than mounting it all. Also cap formatting/highlighting and visible text for oversized SQL, while copying the complete original. A row-only limit is insufficient for wide datasets or large cells; highlighting the full response is the measured regression.

2. **Keep rendering work stable.** Memoize formatting and result preview derivation against the selected call/result content, not the entire growing message list. Do not introduce a parser/highlighter on every streaming update or stringify the whole result just to draw a badge. Reuse the existing code-block presentation with a narrowly scoped plain-text option if needed. Avoid a global rendering change for unrelated code blocks.

3. **Describe payload sizes honestly.** Estimate input from the serialized recorded model-supplied arguments and output from the complete recorded result content, using `ceil(character_count / 4)` as a documented heuristic. Count neither the clipped preview nor model usage, tool definitions, system prompts or transport metadata. Header labels identify input/output and approximation in French/English; accessible help states that these are payload-size estimates, not billed model consumption. A pending/missing output is unavailable rather than zero. An available empty result has a zero-size output. This works for existing history without a backend schema change; provider-exact counts would need a different contract and are outside scope.

4. **Reuse supported-tool boundaries.** Cover the existing tabular discovery, catalog, schema/description, search and query tool names, including their supported historical/MCP aliases. Keep other tools redacted and avoid passing unknown payloads to a new renderer. Failed supported calls retain their safe diagnostics and status.

## Risks / Trade-offs

- The token heuristic varies from each model's tokenizer: label estimates explicitly and keep conversation billing/context totals unchanged.
- A smaller preview hides some values: show row/field/cell limits and provide explicit copying of the recorded response without changing stored data.
- Timing varies by environment: regression tests assert bounded rendering/highlighter inputs; use the captured-response harness for measured before/after evidence, not a brittle wall-clock unit assertion.
- Large histories can trigger repeated renders: test streaming updates and switching/reopening calls, and memoize only computations shown to repeat.
- Scale and multiple pods: all new calculations are local to the selected browser trace. No server call, shared storage, queue, cache or lock is added. Preview work remains bounded as workbook volume grows.

## Migration Plan

Deploy the frontend with no migration or re-ingestion. Existing and live trace shapes remain supported. Rollback consists of reverting this frontend change. Keep private replay data outside the repository and use synthetic wide/long-cell fixtures in committed tests.
