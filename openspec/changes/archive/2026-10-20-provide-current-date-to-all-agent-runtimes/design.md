## Context

`{today}` is rendered only in ReAct/Deep agent prompt templates. The JSON `platform_prompt` is raw text and an admin value replaces its default. Graph model calls do not use that JSON or ReAct prompt composition. Existing agents often store a copy of their original template.

## Goals / Non-Goals

**Goals:** Give existing and new ReAct, Deep, and Graph agents the current UTC date on every model call, without changing stored prompts. Make the instruction date-only when the user asks for today's date.

**Non-Goals:** Expose the current time, infer a user's local timezone, add an MCP tool, or rewrite saved prompts.

## Decisions

- Generate one UTC ISO calendar date instruction in the runtime at call time. ReAct and Deep inject it through the shared model-call middleware into the first `platform_instructions` block, even if no platform file is configured. Their `{today}` template substitution is deferred to the same call so long turns crossing midnight do not present conflicting dates. The admin-editable `platform_prompt` retains its current behavior.
- Graph `NodeContext.invoke_model` and `invoke_structured_model` add the same instruction to their model messages. If the first message is a text system message, prepend the instruction to its content; otherwise prepend a system message. Keep the caller's messages unchanged and use the effective messages for tracing.
- Remove the date lines from generic defaults so the date has one runtime source. Keep `{today}` template support for agents that already use it.

## Risks / Trade-offs

- UTC may differ from a user's local date near midnight. This matches the existing `{today}` token policy.
- Prompt wording guides answers but cannot guarantee model compliance. Tests verify the model input contract.
- Third-party Graph handlers that call `context.model` directly bypass `NodeContext` helpers; the supported SDK graph steps and first-party Graph agents use the helpers.
