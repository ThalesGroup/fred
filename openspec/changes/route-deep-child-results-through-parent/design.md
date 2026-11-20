## Context

See proposal.md for the user-visible failure. `DeepAgentRuntime.build_executor` currently passes the same capability block and composed tool prompt to the parent and native child; only `ask_user` is removed from the child's bound runtime tools. The shared ReAct executor collects `ToolMessage.artifact` sources and UI parts only from root `updates`. It requests LangGraph subgraph events only when platform skills are enabled, and `split_stream_event_mode` labels namespaced non-custom events as `subgraph`.

## Goals / Non-Goals

**Goals:** Keep child work private, give the parent the evidence needed for its answer, and keep capability assembly to one `tools(ctx)` call per selected capability. Preserve existing final-event and history formats across pods and resumed turns.

**Non-Goals:** Publish a child's file, expose its transcript or tool calls, add an output service, or change ReAct and Graph agent behavior.

## Decisions

1. Add a default-enabled Deep child availability declaration to `CapabilityManifest`. During the existing capability assembly pass, retain a child subset of tools, middleware, HITL bindings and prompt metadata from the same instances. Pass that subset to the native child while leaving the parent block unchanged. Mark the current HTML artifact, writable document and PowerPoint file-producing capabilities as parent-only; require the spreadsheet capability to opt out when its pending branch is integrated. A per-tool flag or child-context signal would require filtering middleware tools and guarding side effects in more places. Excluding the whole capability is smaller and matches the current deliverable capabilities.
2. Compose the child's tool prompt and available-tool list from its actual bound tools and filtered capability subset. This prevents the inherited parent prompt and HITL gate from advertising tools that the child cannot call. The child keeps filesystem working-data tools and non-deliverable capabilities. A parent-only tool name has no executable binding in the child graph.
3. Request `subgraphs=True` on Deep turns regardless of platform skills, using an explicit Deep executor setting. The existing stream adapter already distinguishes namespaced events as `subgraph`; the collector needs only the `ToolMessage.artifact` fields in those events. Merge their sources and non-deliverable UI parts into the existing per-turn collections. Do not emit child tool-result, text or thought events, count child model updates again, or let child tool failures replace the parent's answer. Keep normal root event handling intact.
4. Reuse the existing source and UI-part deduplication and final-event persistence path. No new frontend or storage contract is needed. A focused resumed-turn test will verify that repeated evidence is represented once; the collector holds only one turn's results and does not add process-local cross-request state.

## Risks / Trade-offs

- A capability that creates deliverables but omits the new declaration remains callable by children. Document the declaration for capability authors and cover the current producers with a focused test.
- Capability-wide exclusion also hides helper tools in those capabilities from children. The parent can use them; split a mixed capability only if a real child workflow needs its helpers.
- Child fan-out adds artifact merge work on the parent stream. Keep the collection limited to source and non-deliverable parts, and test several children and resume rather than forwarding full child messages.

## Migration Plan

Ship the SDK declaration, capability opt-outs and runtime filtering together. Existing saved agent configuration and conversation records need no migration. Reverting the change restores the previous child tool composition and collection behavior. The Graphify merge is a separate commit and can be removed independently before the final PR.
