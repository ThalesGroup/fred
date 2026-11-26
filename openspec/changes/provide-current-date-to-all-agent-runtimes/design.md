## Context

See proposal.md for the problem. ReAct and Deep compose a system prompt with a read-only `platform_instructions` block ahead of the admin and agent blocks. `{today}` currently renders when that prompt is built. Their model calls share a fixed middleware frame; Graph uses its own messages and the supported `NodeContext` model helpers. No trusted user timezone reaches these runtimes.

The closed, unmerged PR #3179 demonstrated the runtime-level approach but placed date mutation inside `TracingKpiMiddleware`. This design keeps model input policy separate from telemetry.

## Goals / Non-Goals

**Goals:** One date value per model invocation, applied after authored prompt middleware and visible in the effective traced model input. Retire the built-in `{today}` token so the date has one runtime source.

**Non-Goals:** A live clock, local-date inference, a new timezone contract, or interception of third-party Graph code that calls `context.model` directly.

## Decisions

1. **Use the UTC calendar date from the executing pod at each model boundary.** Format it as ISO `YYYY-MM-DD` in model input and include no time-of-day value. There is no trustworthy user timezone in the current runtime context. A per-call value handles a long turn, a retry, a resumed turn on another pod, and the UTC day change. Shared storage would add coordination without improving the ordinary date source; pods must keep their clocks synchronized as they already do for other time-sensitive work. Generating the date when an executor is created would leave a long turn stale.

2. **Use a dedicated ReAct/Deep date middleware immediately outside tracing in both fixed frames.** It runs after capability prompt changes and inside the retry wrapper, so each actual model attempt receives a fresh date and tracing sees the same request. Append the runtime instruction to the composed system message after the authored blocks, leaving the admin `platform_prompt` untouched. A live model test showed that inserting the date in the first `platform_instructions` block let a later saved prompt's stale date win; the final suffix made the runtime date prevail. The prior tracing-middleware placement works while tracing is always installed, but makes prompt correctness depend on observability wiring.

3. **Retire `{today}` from prompt rendering.** Remove it from the `fred-sdk` safe-token registry and the `fred-runtime` token map. Ensure the renderer leaves `{today}` literal even if an internal extra-token map uses that name; other supported tokens keep their existing behavior. Do not rewrite stored agent or library prompts. Remove the token line from the three bundled prompts that use it, and change the creation assistant's guidance so new prompts rely on the runtime date context. Graph and admin prompts already leave the token literal. This removes the second date source and avoids a changing date in the authored prompt prefix.

4. **Add date context in both supported Graph `NodeContext` model helpers.** Make an effective message list without mutating caller messages. Append the runtime instruction to the last text system message when present; otherwise add a system message before the conversation. Use the effective list for both the provider call and content tracing. This keeps Graph's existing prompt ownership and covers its streaming and structured paths without wrapping the raw model property.

5. **Guide outputs through the same instruction.** For an ordinary request for today's date, ask for the date alone, without a time or UTC label. For an explicitly local-date request, tell the model that only the UTC date is known. The date is a platform fact for the real present day; explicit fictional or historical tasks remain valid. Tests assert the model-input contract because final phrasing depends on model compliance.

## Risks / Trade-offs

- UTC can differ from the date in France near midnight - accepted for this issue; the instruction qualifies explicit local-date requests. An ordinary date answer intentionally omits the UTC label.
- The date is the last suffix of the ReAct/Deep system message. The authored prompt remains a stable prefix across UTC midnight, and the date fragment remains stable within each UTC day. Exact provider cache behavior is outside runtime control.
- Third-party Graph nodes can bypass the supported helpers through `context.model` - document the boundary; first-party Graph agents use the helpers.
- Existing stored ReAct/Deep templates and attached context prompts containing `{today}` will now expose that literal text to the model. This is an accepted prompt-template compatibility break; the runtime still supplies the actual date, and no stored prompt is migrated.
- Replicas with skewed clocks can briefly disagree near midnight - use each pod's UTC clock and normal clock synchronization; no process-local cache or cross-request state is needed.

## Migration Plan

Deploy updated pods using the new `fred-runtime` and bundled prompts; existing agent instances need no prompt or data migration. Validate a date request against existing ReAct, Deep, and Graph agents and the UTC rollover case. Existing stored `{today}` text becomes literal on updated pods, while older external images retain their previous substitution behavior until updated. Rollback restores the previous runtime behavior; stored prompt data is unchanged.
