## Why

[#3458](https://github.com/ThalesGroup/fred/issues/3458): caught tabular MCP failures can become an empty `Tool error:` for the model, while the chat drawer shows only a failed status and duration. Recurrent document-reference and DuckDB mistakes also need short guidance at the tool boundary.

## What Changes

- Give the model a non-empty Fred-owned failure explanation and next action; preserve the existing curated `read_query` HTTP 400 diagnostic and authority-stop behavior.
- Make the existing trace drawer an explanatory view: show the failed action, the recorded business arguments and the error preserved by the trusted boundary. Do not show a next-step section or recovery advice. Retain equivalent live/history behavior.
- Review and rewrite the whole tabular prompt for a clear discovery/schema/query/results flow, removing repetition while preserving access and type rules. Clarify argument descriptions and retain at most one compact date-arithmetic example.
- On successful queries returning zero rows, add the explicit message "Requête exécutée avec succès : 0 ligne correspondant aux conditions." Preserve success status, empty rows and the structured SQL result. Instruct the model to reuse successful results and correct unexpected filters before retrying; do not add duplicate-call suppression or result caching.
- Show tabular document selectors, SQL, search terms and result limits as recorded in the call. Keep credentials, injected authentication/scope internals and arbitrary provider errors outside the user-facing detail.

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
- Add an optional `message` to Knowledge Flow's SQL response; event and history shapes remain unchanged. No database table, deployment setting or dependency is required. Regenerate Knowledge Flow OpenAPI/client artifacts.
- Update the runtime contract, trace UX guidance and one English operator migration note. The completed `reliable-agent-work-completion` and SQL-error work remain historical dependencies, not new task containers.
