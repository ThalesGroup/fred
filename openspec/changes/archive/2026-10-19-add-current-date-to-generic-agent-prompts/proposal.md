## Why

Generic ReAct and Deep assistants can guess today's date because their shipped default prompts omit Fred's existing `{today}` token. Give them the execution date when a user asks for it.

## What Changes

- Add `{today}` to the English and French default system prompts of the generic ReAct and Deep assistants.
- Tell these assistants to answer date requests with the date, without a time.
- Keep the existing runtime token renderer and editable prompt override behavior.
- Apply the new defaults to newly created instances and instances without a saved prompt value; stored prompts are not rewritten.

## Capabilities

### New Capabilities

- `generic-agent-prompts`: Default prompt behavior of Fred's generic ReAct and Deep assistants.

### Modified Capabilities

None.

## Impact

- Affects the two generic assistant definitions in `apps/fred-agents/fred_agents/` and focused prompt tests.
- No API, MCP catalog, dependency, or stored instance migration changes.
- Tracks issue #3178.
