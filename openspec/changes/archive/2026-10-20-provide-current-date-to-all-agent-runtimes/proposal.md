## Why

Agents with saved prompts can guess today's date because the execution date is available only when an agent template explicitly uses `{today}`. A change to the default platform prompt would miss saved admin values and Graph agents.

## What Changes

- Provide the current UTC calendar date at model call time for ReAct, Deep, and Graph agents.
- Tell the model to answer requests for today's date with the date and no time.
- Preserve stored agent prompts and admin platform prompts without requiring edits to existing instances.
- Remove the four generic prompt additions superseded by runtime-wide context.

## Capabilities

### New Capabilities

- `agent-current-date-context`: Runtime date context shared across agent execution models.

### Modified Capabilities

None.

## Impact

- Changes shared ReAct/Deep model-call middleware and Graph model invocation in `libs/fred-runtime`.
- Updates focused tests, prompt documentation, and the migration note.
- No API, MCP tool, deployment setting, or stored data migration.
- Tracks issue #3178.
