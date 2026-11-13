## Context

See proposal.md for the requested behavior. `TraceDetailDrawer` already parses the recorded SQL response and displays it through the existing syntax-colored `CodeBlock`. `previewTabularRows` bounds SQL and search previews to five rows; SQL passes `allColumns: true`. `TabularToolDetail` already uses a small design-system text button to reveal other lists in batches of ten. The token-counting proposal had no runtime implementation and is withdrawn at the user's request.

## Goals / Non-Goals

Keep the change in recorded-result inspection. Do not execute SQL, fetch omitted database rows, add token measurements, change backend result limits or alter unrelated tabular-search previews.

## Decisions

1. Keep the common helper's five-row default for existing consumers and add an explicit visible-row limit for SQL. The SQL detail owns a ten-row page size, capped at the recorded row count, instead of changing a global constant used by search results.
2. Reuse the existing small text-button pattern below the JSON block. Each click appends up to ten already-recorded rows to the visible prefix. Use French/English row-specific labels with the actual next count, including singular remainders; hide the button once exhausted.
3. Scope expansion to the selected session/exchange/tool-call identity. Switching calls or closing/reopening resets the preview to ten; unrelated stream updates keep the current expansion. Memoize clipped rows and JSON using the result and visible count so unchanged stream events do not repeat formatting/highlighting.
4. Preserve the existing drawer, SQL/JSON colors, every complete column name, bounded long cells, full-response copy, and tool-owned notices. The compact preview sentence reflects the currently visible count. No token badge or model-usage paragraph is introduced.
5. Delete the unused `ModelCallTokenUsage`/`model_call_usage` attribution chain from contracts, extraction, runtime orchestration, history builders and frontend SSE propagation; regenerate runtime OpenAPI/client from source. Retain provider usage normalization, aggregate `token_usage` and final `context_tokens`, which support conversation accounting. Preserve historical records and tolerant metadata parsing; no backfill or database rewrite is needed. Replace attribution-only tests with focused absence/accounting/old-history compatibility checks where they protect the changed boundary.

## Risks / Trade-offs

- Revealing more rows increases deliberate rendering work. Initial formatting/highlighting must depend on at most ten rows, not the entire result; verify wide recorded results, several increments and unrelated streaming using the real renderer. Do not pre-render hidden rows.
- A recorded result may itself be truncated by tool limits. The button can reveal only recorded rows; preserve the tool's own result message and do not imply that a click fetches more database data.
- State leaking between calls would show the wrong initial count. Validate different calls with identical SQL as well as reopening and live updates.
- This is presentation state confined to a browser. No cross-pod state, database query, connection pool, shared cache or additional request is introduced; backend concurrency and result contracts are unchanged.

## Migration Plan

Deploy SDK/runtime and frontend normally. Existing recordings need no migration or query replay. Update the existing runtime contract, UX and operator note during implementation; older readers remain compatible with absent optional attribution fields. A normal rollback restores the earlier behavior.
