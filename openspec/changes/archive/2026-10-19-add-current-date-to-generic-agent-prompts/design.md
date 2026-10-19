## Context

Fred's ReAct and Deep prompt renderer already expands `{today}` to the current UTC calendar date on execution. Both generic assistant definitions provide English and French prompt defaults through `prompts.system`; neither currently includes the token.

## Goals / Non-Goals

**Goals:** Make the existing token available in both shipped generic assistant defaults and give clear date-only response guidance.

**Non-Goals:** Change timezone policy, expose the clock, add an MCP tool, or rewrite existing stored custom prompts.

## Decisions

- Add one concise instruction containing `{today}` to each localized default. This uses the established renderer and keeps the value current across executions. A fixed date or separate tool would introduce needless stale data or an extra capability.
- Keep the instruction in the existing agent prompts, not the platform prompt, so it affects the two requested templates only.

## Risks / Trade-offs

- UTC may differ from a user's local calendar date around midnight. The existing token defines that behavior; any timezone policy change needs separate scope.
- Prompt text guides model output but cannot enforce it. Focused tests will check the rendered input contract, not claim deterministic model compliance.
- Existing instances created in the UI often store a copy of the old default prompt. Those copies remain unchanged; users can add `{today}` to them when editing the instance.
