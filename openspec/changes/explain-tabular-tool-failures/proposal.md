## Why

[#3458](https://github.com/ThalesGroup/fred/issues/3458): caught tabular MCP failures can become an empty `Tool error:` for the model, while the chat drawer shows only a failed status and duration. Recurrent document-reference and DuckDB mistakes also need short guidance at the tool boundary.

## What Changes

- Give caught MCP failures a non-empty Fred-owned explanation and next action; preserve the existing curated `read_query` HTTP 400 diagnostic and authority-stop behavior.
- Explain failures in the existing trace drawer, including the action, safe cause, recovery guidance and authorized document name when available. Retain attempted SQL for `read_query` and equivalent live/history behavior.
- Clarify document UIDs, SQL aliases and the DuckDB dialect in parameter descriptions. Add only one compact date-arithmetic example and a short reminder to use exact stored text values.
- Keep arbitrary provider errors, credentials, private URLs and unrelated arguments outside the user-facing detail.

Authentication changes, model changes, automatic filename-to-UID substitution, caching and duplicate-call enforcement are out of scope. The API-versus-browser and repeated-success investigations inform this change but do not authorize those separate behavioral changes.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `mcp-capabilities`: non-empty bounded failure feedback and its safe display in the existing tool trace.
- `tabular-query-safety`: concise document-reference and DuckDB guidance without relaxing SQL or authorization validation.

## Impact

- Runtime: `common/context_aware_tool.py`, `react/react_tool_rendering.py`, resolution tests and the existing MCP mount's safe error classification where needed.
- Knowledge Flow: tabular parameter descriptions and focused controller/schema tests.
- MCP capability: `prompts/tabular.md` and instruction tests.
- Frontend: `traceUtils.ts`, `TraceDetailDrawer`, translations and focused tests.
- Reuse existing result content, event and history shapes; no database table, deployment setting or dependency is required. Regenerate Knowledge Flow OpenAPI/client artifacts when parameter descriptions change.
- Update the runtime contract, trace UX guidance and one English operator migration note. The completed `reliable-agent-work-completion` and SQL-error work remain historical dependencies, not new task containers.
