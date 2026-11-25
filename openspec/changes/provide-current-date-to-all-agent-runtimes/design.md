## Context

See proposal.md for the problem. ReAct and Deep compose a system prompt with a read-only `platform_instructions` block ahead of the admin and agent blocks. `{today}` currently renders when that prompt is built. Their model calls share a fixed middleware frame; Graph uses its own messages and the supported `NodeContext` model helpers. No trusted user timezone reaches these runtimes.

The closed, unmerged PR #3179 demonstrated the runtime-level approach but placed date mutation inside `TracingKpiMiddleware`. This design keeps model input policy separate from telemetry.

## Goals / Non-Goals

**Goals:** One date value per model invocation, applied after authored prompt middleware and visible in the effective traced model input. Keep `{today}` as an optional explicit-placement token in ReAct/Deep templates, consistent with that value.

**Non-Goals:** A live clock, local-date inference, a new timezone contract, or interception of third-party Graph code that calls `context.model` directly.

## Decisions

1. **Use the UTC calendar date from the executing pod at each model boundary.** Format it as ISO `YYYY-MM-DD` in model input and include no time-of-day value. There is no trustworthy user timezone in the current runtime context. A per-call value handles a long turn, a retry, a resumed turn on another pod, and the UTC day change. Shared storage would add coordination without improving the ordinary date source; pods must keep their clocks synchronized as they already do for other time-sensitive work. Generating the date when an executor is created would leave a long turn stale.

2. **Use a dedicated ReAct/Deep date middleware immediately outside tracing in both fixed frames.** It runs after capability prompt changes and inside the retry wrapper, so each actual model attempt receives a fresh date and tracing sees the same request. Insert the instruction at the end of the read-only `platform_instructions` block, or create that block when absent. This preserves the documented block precedence over an outdated saved prompt while leaving the admin `platform_prompt` untouched. The prior tracing-middleware placement works while tracing is always installed, but makes prompt correctness depend on observability wiring.

3. **Keep `{today}` for explicit date placement, not date awareness.** Defer its substitution in ReAct/Deep agent templates and attached session context prompts until the date middleware runs. Render those supported tokens to a runtime-owned sentinel, then replace it with the one date value used by the new instruction. Other safe tokens keep their existing rendering behavior. The admin platform prompt override and Graph-authored prompts retain literal `{today}`; neither enters this rendering path. Rebuilding the entire system prompt on each model call would spread prompt assembly into the hot path. Replacing literal `{today}` at call time would reinterpret authored text that is currently left literal on these other surfaces.

4. **Add date context in both supported Graph `NodeContext` model helpers.** Make an effective message list without mutating caller messages. Append the runtime instruction to the first text system message when present; otherwise add a system message before the conversation. Use the effective list for both the provider call and content tracing. This keeps Graph's existing prompt ownership and covers its streaming and structured paths without wrapping the raw model property.

5. **Guide outputs through the same instruction.** For an ordinary request for today's date, ask for the date alone, without a time or UTC label. For an explicitly local-date request, tell the model that only the UTC date is known. The date is a platform fact for the real present day; explicit fictional or historical tasks remain valid. Tests assert the model-input contract because final phrasing depends on model compliance.

## Risks / Trade-offs

- UTC can differ from the date in France near midnight - accepted for this issue; the instruction qualifies explicit local-date requests. An ordinary date answer intentionally omits the UTC label.
- The date changes the prompt prefix at UTC midnight - keep the static platform instructions before the date and supply no changing clock value, so the date fragment remains stable for each UTC day. Exact provider cache behavior is outside runtime control.
- Third-party Graph nodes can bypass the supported helpers through `context.model` - document the boundary; first-party Graph agents use the helpers.
- An existing ReAct/Deep template containing `{today}` repeats the date already supplied by the middleware and may change an earlier prompt prefix at UTC midnight. Keep that compatibility, but stop recommending the token merely to give a new agent date awareness.
- Replicas with skewed clocks can briefly disagree near midnight - use each pod's UTC clock and normal clock synchronization; no process-local cache or cross-request state is needed.

## Migration Plan

Deploy updated pods using the new `fred-runtime`; existing agent instances need no prompt or data migration. Validate a date request against existing ReAct, Deep, and Graph agents and the UTC rollover case. Rollback restores the previous runtime behavior; stored prompts and public contracts are unchanged. External pods still running older images retain their previous behavior until updated.
