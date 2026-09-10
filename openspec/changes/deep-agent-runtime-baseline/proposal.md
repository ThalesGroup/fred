## Why

`DeepAgentRuntime` existed and was directly unit-tested, but `agent_app.py`'s per-turn dispatch
never actually routed to it: because `DeepAgentDefinition` subclasses `ReActAgentDefinition`, every
Deep agent — including `fred.github.deep_assistant` — silently ran on plain `ReActRuntime` instead
of the `deepagents` planner it was authored for. Fixing dispatch alone would have introduced a
second, worse regression: `DeepAgentRuntime.build_executor` never read the selected capability
block, and any capability declaring a `HitlSpec` (`document_extract`, `document_summarize`) crashed
a Deep turn before any LLM call, regardless of whether that binding would ever actually fire. This
change fixes both defects and brings Deep to full HITL parity with ReAct — capability-declared and
operator-configured approval both work, through the one Fred gate both runtimes already share —
rather than leaving Deep with a narrower, asymmetric subset of ReAct's approval behavior.

## What Changes

- `agent_app.py` dispatches `DeepAgentDefinition` to `DeepAgentRuntime` instead of falling through to
  `ReActRuntime` (committed on this branch; RUNTIME-EXECUTION-CONTRACT.md links to the
  `deep-agent-runtime` OpenSpec capability for the durable behavioral record).
- `DeepAgentRuntime.build_executor` reads the selected capability block and threads its tools, MCP
  prompt groups and middleware into the compiled `deepagents` graph, the same way
  `_create_compiled_react_agent` does for ReAct.
- Deep reuses Fred's existing `TracingKpiMiddleware` and `ToolObservabilityMiddleware`, so a Deep turn
  emits the same `[LLM][CALL]`/`[LLM][RESPONSE]` logs, `llm.call_latency_ms` KPI and
  `agent.tool.invocation.*` audit events ReAct already produces.
- `FredHitlMiddleware` — the same middleware `ReActRuntime` already uses — is composed into Deep's
  middleware list, in the same relative position `build_react_platform_middleware_frame` uses. This
  replaces the blanket `NotImplementedError` that previously hard-rejected any Deep turn selecting a
  capability with a non-empty `hitl_specs()`.
- Deep's separate build-time rejection of an enabled operator `ToolApprovalPolicy` is also removed.
  Both capability-declared and operator-configured approval now route through the one already-shared
  `FredHitlMiddleware` gate — no second HITL mechanism is introduced for either runtime.
- A gated tool call — capability-declared or operator-configured — can no-op (its condition does not
  apply), pause and resume on `proceed`, or pause and skip the call on `cancel`, on both ReAct and
  Deep, through Fred's existing `AwaitingHumanRuntimeEvent`/`HumanInputRequest` transport contract.
  This is proven at two levels: a real compiled `deepagents` graph with a real LangGraph
  `interrupt()`/`Command(resume=...)`, and a real `_TransportBackedReActExecutor` run confirming the
  pause reaches Fred's own event/resume layer, not only the underlying graph library.
- ReAct's own execution path is unchanged; it remains the comparison baseline for this change's
  acceptance evidence.

## Capabilities

### New Capabilities

- `deep-agent-runtime`: Deep agents dispatch to `DeepAgentRuntime`, receive their selected
  capability's tools/prompt groups/middleware, and emit the same tracing/KPI/audit signal ReAct
  does. This becomes the durable behavioral record for Deep's runtime baseline once this change is
  archived — see `design.md` D5.
- `agent-human-approval`: capability-declared and operator-configured approval both gate a tool call
  on ReAct and on Deep, through the one Fred HITL gate and the one `HumanInputRequest` proceed/cancel
  contract. `GraphRuntime` is out of scope — it keeps its own separate HITL lifecycle.

### Modified Capabilities

None.

## Impact

- Runtime: `libs/fred-runtime/fred_runtime/deep/deep_runtime.py` (capability wiring, middleware
  assembly, operator-policy rejection removed), `react/react_runtime.py` (runtime-class-name logging
  only, no ReAct behavior change; already committed).
- Tests: `test_deep_agent_dispatch.py` (basedpyright-clean), `test_deep_agent_middleware.py`,
  `test_deep_agent_hitl_integration.py` (real compiled-graph HITL proof, capability and operator;
  plus a transport-level proof through `_TransportBackedReActExecutor`).
- Docs: `RUNTIME-EXECUTION-CONTRACT.md` keeps only compact architecture/invariants for Deep and links
  to this change's two OpenSpec capabilities as the durable behavioral source, once archived (see
  `design.md` D5 and `tasks.md`'s closing group).
- Manual acceptance evidence: one witnessed run of the public NOVA-DOC factual question
  (`fred-corpus`'s `public-tender-response` knowledge base) against both `fred.github.deep_assistant`
  and `fred.github.assistant` (ReAct), each producing the same correct grounded answer. Both runs
  invoked only `search_documents_using_vectorization` — no filesystem tool, no Workspace object, no
  S3/SeaweedFS write. See `design.md` for the recorded detail and what this evidence does and does
  not prove.

## Non-goals

- `WorkspaceService`, `FredWorkspaceBackend`, and M2M binding validation — tracked separately under
  #2328 and #2498, not part of this change.
- Passing `backend=`/`CompositeBackend` to `create_deep_agent` — Deep's filesystem tools stay on
  `deepagents`'s own conversation-scoped checkpoint filesystem (see `design.md` D2); no durable,
  user-visible Workspace exists yet.
- The multi-document tender scenario, its rubric, and any deliverable-publication proof — a future
  slice once #2328/#2498 land, not evidence for this change.
- Advanced planning, sub-agent orchestration, and `GraphRuntime` HITL — out of scope; see `design.md`
  for `GraphRuntime`'s current, unrelated HITL lifecycle.
- The `deepagents`-built-in-filesystem-tool-name-overlap case is a regression test, not a durable
  product requirement — no shipped capability gates a filesystem tool today (see `design.md` D3).
