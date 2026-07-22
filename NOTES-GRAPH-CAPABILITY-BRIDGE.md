# NOTES — Graph agents ↔ AgentCapability bridge (branch `consolidation-22-07`)

Tracker for the in-progress work making `AgentCapability` (currently ReAct-only for
its tool-carrying half) usable from Graph agents too, without polluting the Graph
SDK surface. Companion to the chat conversation that produced it — this file is the
durable record; re-read it before resuming work in a fresh session.

## Design invariants (non-negotiable — restate before any code change)

- **Invariant A — Graph SDK stays untouched.** `fred_sdk/graph/*`
  (`GraphNodeContext.invoke_runtime_tool`, `invoke_tool`, etc.) gets zero new
  imports, zero new concepts. A Graph author never learns "capability" exists.
- **Invariant B — the capability contract is redesigned, not patched.**
  `AgentCapability.tools()` becomes the primary, execution-model-agnostic
  authoring surface; `middleware()` becomes the ReAct-loop-only escape hatch
  with a generic default built from `tools()`. Not a bolt-on `getattr` hack —
  a inversion of which method is primary.

## Why (recap)

`_build_capability_block` (`agent_app.py`) raises `CapabilityError` today for any
non-ReAct definition selecting a real (non-MCP) capability. MCP-server
capabilities (`McpCapability`) already bypass this cleanly: their actual tool
loading goes through `_active_mcp_server_refs` → `FredMcpToolProvider`, a service
`GraphRuntime` and `ReActRuntime` both consume identically — only their
prompt-fragment middleware is ReAct-only. Package capabilities (`document_access`)
have no equivalent second path: their tool lives only in
`AgentMiddleware.tools`, read exclusively by `create_agent()`.

## Plan

### Phase 1 — `fred-sdk` contract change — DONE (2026-07-22)

File: `libs/fred-sdk/fred_sdk/contracts/capability/base.py`
- Added `tools(self, ctx) -> Sequence[BaseTool]` (default: `()`).
- `middleware()` lost `@abstractmethod`; default implementation wraps
  `self.tools(ctx)` in one generic `_ToolCarrierMiddleware` (new, minimal
  class: `self.tools = list(tools)`, nothing else — module-level import of
  `AgentMiddleware` promoted from `TYPE_CHECKING`-only to a real import, since
  `langchain` is already a hard runtime dependency of fred-sdk).
- Migrated `DocumentAccessCapability`
  (`libs/fred-runtime/fred_runtime/capabilities/document_access/capability.py`)
  to implement `tools()` only; deleted `_DocumentAccessMiddleware`.
  `McpCapability` (`fred_runtime/capabilities/mcp.py`) untouched — its
  contract (`middleware()`-only, prompt fragment) is legitimately ReAct-only
  and stays that way.
- Existing `test_capability_document_access_1906.py` needed **zero changes**:
  it drives the capability through `cap.middleware(ctx)`, which the new
  default wrapper still serves identically.

**Return-convention correction — the "Return-type fix" bullet above was
WRONG in its mechanism and its prescription. Do not re-derive this; the
finding below is settled by a real invocation test, not inspection.**

What was tested (`libs/fred-runtime/tests/test_capability_tool_return_convention.py`):
`document_access`'s real tool (`@tool(..., response_format="content_and_artifact")`)
and a synthetic bare-`ToolInvocationResult` tool (matching
`KfVectorSearchToolkit`'s convention), each invoked BOTH ways — a plain args
dict (`tool.ainvoke({"question": ...})`, what `invoke_runtime_tool` and
`_resolve_runtime_provider_tool` both do) and a real `ToolCall` dict
(`tool.ainvoke({"type": "tool_call", "name": ..., "args": ..., "id": ...})`,
what `create_agent()`'s actual ReAct tool-calling loop does).

What was found:
- `content_and_artifact` + plain-dict invoke: the artifact is not merely
  "collapsed to a tuple" as originally assumed — LangChain drops it entirely
  and returns a **bare content string**, not even a 2-tuple. There is no
  tuple for `_normalize_runtime_tool_output` (`graph_runtime.py`) to unpack;
  its 2-tuple-handling branch is dead code for this tool shape. (Confirmed:
  its branch fires only for a tool returning a genuine bare Python tuple with
  no `response_format` set — a different, unrelated case.)
- `content_and_artifact` + `ToolCall`-dict invoke: works correctly today —
  `ToolMessage.artifact` carries the full `ToolInvocationResult`, `.sources`
  intact. This is the ONLY path `document_access`'s tool is exercised through
  currently (and through Phase 1 — nothing yet merges it into a plain-dict
  invocation site; that's Phase 4).
- Bare `ToolInvocationResult` return (no `response_format`) + plain-dict
  invoke: survives intact — this is why `KfVectorSearchToolkit` uses it, and
  the ONLY invocation path it needs to survive.
- Bare `ToolInvocationResult` return + `ToolCall`-dict invoke: **breaks** —
  LangChain stringifies the whole model into `ToolMessage.content` via
  `str(model)` and never populates `.artifact`.

Conclusion: there is no single-tool return convention correct on both
invocation paths with a plain `@tool`. `content_and_artifact` is right for
create_agent()/ReAct; bare `ToolInvocationResult` is right for plain-dict
invocation. **Decision for Phase 1: kept `document_access`'s tool on
`content_and_artifact`, unchanged** — it is already correct for the only path
it runs through today, and changing it now would have been a regression with
no corresponding benefit (nothing consumes it via plain-dict invoke yet).

**Consequence for Phase 2+ (flagged, not solved here):** the original
Phase-1 prescription ("migrate document_access's tool to return
`ToolInvocationResult` directly") would have silently broken the ReAct
Sources panel the first time it shipped, because it did not account for the
`ToolCall`-invoke regression above. Whichever phase actually merges capability
tools into Graph's plain-dict `invoke_runtime_tool` path (Phase 4, as the
`CapabilityAgentBlock.tools` field lands in Phase 2) must resolve this at the
**consumption seam**, not by changing the tool's return shape again — e.g. the
default tool-carrier middleware (or the Phase-4 merge step) adapting a
`content_and_artifact` LangChain tool into something that also survives a
plain-dict call, reusing `_resolve_runtime_provider_tool`'s
already-established three-way return-shape handling as the template rather
than inventing new unwrapping logic. This is real, unfinished design work for
Phase 2/4 — call it out explicitly when picking that phase back up.

### Phase 2 — `CapabilityAgentBlock` gains a `tools` field
File: `libs/fred-runtime/fred_runtime/capabilities/assembly.py`
- `CapabilityAgentBlock`: add `tools: tuple[BaseTool, ...]`.
- `build_capability_agent_block`: replace the ad-hoc `tools_by_name` loop
  (currently private to HITL-tool binding, line ~337) with a call to
  `capability.tools(ctx)` per selected capability, deduped by name, stored in
  the new field. HITL binding reads this same field instead of re-scanning
  `.tools` on every middleware — one source of truth, two consumers.
- Collision guard: raise a named error if a capability tool name collides with
  an MCP-resolved runtime tool name for the same agent (never silently shadow).

### Phase 3 — remove the two ReAct-only gates
File: `libs/fred-runtime/fred_runtime/app/agent_app.py`
- `_effective_capability_ids` (~line 2222): drop the
  `isinstance(definition, ReActAgentDefinition)` early return. Prerequisite —
  without this, `_build_capability_block` never receives anything to assemble
  for a Graph agent.
- `_build_capability_block` (~line 2323): drop the `CapabilityError`-raising
  branch entirely. The block is now built **uniformly** for both agent kinds;
  each runtime consumes the half that concerns it. No more "capabilities
  don't work on Graph" branch anywhere in the code.

### Phase 4 — `GraphRuntime` consumes `capability_block.tools`
File: `libs/fred-runtime/fred_runtime/graph/graph_runtime.py`
- `GraphRuntime.__init__` gains `capability_block: CapabilityAgentBlock | None = None`.
- `build_executor` (~line 1851): merge `capability_block.tools` into the
  `runtime_tools` tuple before constructing `_DeterministicGraphExecutor` — no
  change needed to the executor itself (`{tool.name: tool for tool in
  runtime_tools}` stays as-is).

### Phase 5 — wire it at the one call site
File: `agent_app.py` (~line 2531-2535), the only place that constructs
`GraphRuntime` — pass `capability_block=capability_block` (already computed
above for the ReAct branch).

### Phase 6 — end-to-end proof
- Extend `apps/fred-agents/fred_agents/test_assistant/graph_agent.py` with a
  scenario: node calls `document_access`'s tool via `invoke_runtime_tool`, then
  a `choice_step` HITL gate, then branches on the answer — `document_access`
  selected via `tuning.selected_capability_ids`, not `default_mcp_servers`.
- Unit tests: update `test_capability_document_access_1906.py` for the new
  `tools()` contract; add a `test_graph_capability_bridge.py` verifying
  `GraphRuntime` exposes capability tools to `invoke_runtime_tool`.

### Explicitly out of scope for this prototype
- Chat controls / composer widgets for Graph (library picker in the chat UI) —
  control-plane + frontend, separate chantier.
- Frontend Tools-tab picker filtering by template kind — no longer a
  correctness bug (Graph genuinely supports capabilities now), just a
  separate UX question.
- `McpCapability` — zero changes, its lane stays valid and separate.

## Validation against real target agents (2026-07-22)

Read in full to check the plan against reality, not just theory. Both repos pin
older SDK versions (`dt-agents`: `fred-sdk>=3.1.0`; `fred-samples`:
`fred-sdk>=2.0.5` — the "old versions" the user referred to).

**`~/Fred/dt-agents/agents/fred_dt_agents/aegis`** (Corrective-RAG + Self-RAG
graph agent) and **`dva_risk_validator_team`** (graph + ReAct QA agent + a
`TeamAgent` router) — neither uses `document_access` or any package capability.
Both use:
- `default_mcp_servers = (MCPServerRef(id=MCP_SERVER_KNOWLEDGE_FLOW_TEXT),)` —
  the `McpCapability` lane, already Graph-compatible today (unchanged by this
  plan).
- `declared_tool_refs = (ToolRefRequirement(tool_ref=TOOL_REF_KNOWLEDGE_SEARCH, ...),)`
  + `context.invoke_tool(TOOL_REF_KNOWLEDGE_SEARCH, {...})` — a **third,
  already execution-model-agnostic lane** I had not previously mapped:
  `GraphNodeContext.invoke_tool` (`graph_runtime.py:610`) resolves a small,
  fixed set of platform built-in tool refs (`TOOL_REF_KNOWLEDGE_SEARCH`,
  `TOOL_REF_ARTIFACTS_PUBLISH_TEXT`, `TOOL_REF_RESOURCES_FETCH_TEXT`,
  `TOOL_REF_TRACES_SUMMARIZE_CONVERSATION`) through `services.tool_invoker`
  (`ToolInvokerPort`), identically for ReAct and Graph, since day one.
  This is proof-of-concept that "one implementation, both agent kinds" is an
  established pattern here — it just isn't extensible (no package registry,
  no per-instance config, no team-scoping), which is exactly why it can't
  serve as `document_access`'s host: it's a fixed built-in dispatch table, not
  an installable-capability mechanism.
- Per-instance tuning (bound libraries would be, e.g., `settings.top_k`,
  `settings.min_relevance_score`) is expressed today as hand-rolled
  `FieldSpec` tuples read via `context.tuning_values` — each agent reinvents
  its own scoping fields instead of reusing a shared `DocumentAccessConfig`.
  **This is the actual value the bridge adds for agents like these**: not new
  search functionality (they already have that), but the option to reuse one
  shared, configurable capability instead of hand-rolling equivalent fields
  per agent.

**`~/Fred/fred-samples/agents/fred_samples_agents/cvem_watch`** (introduced
today, uncommitted — `git status` shows it `??`; this is the "team/demo agent"
this morning) — squarely in the `default_mcp_servers` lane
(`mcp-knowledge-flow-mcp-tabular`, `mcp-knowledge-flow-mcp-text`), calling
tools through a hand-written `sop.py` helper module. Does not touch
capabilities at all.

**Conclusion:** all three target agents run today, unmodified, on mechanisms
this plan does not touch (`McpCapability`/`default_mcp_servers` resolution,
`declared_tool_refs`/`tool_invoker`, `invoke_runtime_tool`'s existing
dict-lookup). The bridge is strictly additive — it does not change whether
these agents work, only whether a *future* Graph agent can reuse
`document_access` (or a future capability) instead of hand-rolling its own
`FieldSpec`-based scoping. Zero regression risk to the three agents from
Phases 1-5 as designed.

**One concrete correction Phase 1 must carry — superseded, see Phase 1 section
above.** This paragraph originally predicted `document_access`'s tool needed
its return convention changed to bare `ToolInvocationResult`
(`KfVectorSearchToolkit`'s pattern). Phase 1's actual invocation testing found
that "fix" is itself wrong: bare `ToolInvocationResult` return breaks
`create_agent()`'s real `ToolCall`-based invocation (stringifies the result,
drops `.artifact`) — the ONLY path `document_access`'s tool runs through today.
Phase 1 kept `content_and_artifact` unchanged; the plain-dict-invocation
problem this paragraph correctly identified is real but unsolved, deferred to
Phase 2/4 as a consumption-seam adapter, not a tool return-shape change.

## Status

Phase 1 implemented and verified (2026-07-22): `libs/fred-sdk` and
`libs/fred-runtime` both pass `make code-quality && make test`
(233 and 569 tests respectively, zero regressions, no other test file needed
changes). Phases 2-6 not started.

Next action: Phase 2 (`CapabilityAgentBlock.tools` field in `assembly.py`) —
when picking it up, read the Phase 1 return-convention finding above first;
the plain-dict-invocation adapter problem it flags becomes real once Phase 4
wires capability tools into `GraphRuntime.runtime_tools`.
