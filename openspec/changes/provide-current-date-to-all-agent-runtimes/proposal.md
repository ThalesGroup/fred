## Why

Existing agents can guess today's date because ReAct and Deep expose it only when a saved prompt uses `{today}`, while Graph builds its own model messages. Changing bundled or admin-editable prompts would not reach every existing agent instance.

## What Changes

- Supply the current UTC calendar date at every supported ReAct, Deep, and Graph model invocation, including Deep child calls and Graph streaming and structured calls.
- Retire `{today}` as a supported prompt token. Existing stored prompts are not rewritten; any `{today}` they contain becomes literal text. Remove it from bundled prompts, the safe-token registry, and prompt-authoring guidance.
- Guide the model to answer ordinary requests for today's date with a date only. For an explicitly requested local date, make clear that only the UTC date is available.
- Preserve stored agent prompts and admin platform prompt overrides. Treat the runtime date as the reference for the real current date when an older prompt conflicts with it.

## Capabilities

### New Capabilities

- `agent-current-date-context`: Runtime-supplied current date for supported agent model calls and date answers.

### Modified Capabilities

None.

## Impact

- `fred-runtime` ReAct/Deep model-call framing, prompt token rendering, and Graph `NodeContext` model helpers; `fred-sdk` safe-token registry; bundled agent prompts; focused tests.
- Prompt behavior documentation and the required operator migration note.
- Existing instances receive the change when their runtime pods are updated. Older external pod images remain on their existing behavior.
- No current-time value, user-timezone field, MCP tool, HTTP API change, dependency, or stored-data migration. Retiring `{today}` changes the SDK's advertised prompt-token contract.
