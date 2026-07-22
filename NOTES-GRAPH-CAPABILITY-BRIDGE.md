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

### Phase 2 — `CapabilityAgentBlock` gains a `tools` field — DONE (2026-07-22)
File: `libs/fred-runtime/fred_runtime/capabilities/assembly.py`
- `CapabilityAgentBlock`: added `tools: tuple[BaseTool, ...]`.
- `build_capability_agent_block`: the old `tools_by_name` loop (scanning
  `getattr(mw, "tools", None)` off each capability's middleware stack, private
  to HITL-tool binding) is gone. Replaced by a direct `capability.tools(ctx)`
  call per selected capability (same `sorted(contexts)` order), collected into
  one dict deduped by tool name. That one map is now `CapabilityAgentBlock.tools`
  AND what HITL binding reads (`tools_by_name.get(spec.tool)`) — one source of
  truth, two consumers, exactly as planned. `capability.middleware(ctx)` is
  still called too (unchanged) — it's the only source for non-tool middleware
  (prompt fragments, hooks) and, for `tools()`-based capabilities, the default
  `middleware()` wraps the same `tools()` output a second time. That's a
  redundant *call*, not redundant *code* (confirmed against `base.py` before
  starting) — cheap (plain `@tool`-decorated closures), and avoiding it would
  require special-casing `McpCapability`'s legitimate direct-`middleware()`
  override, which is out of scope for the minimal change asked for here.

- **Collision decision 1 — two capabilities, same tool name (in scope, implemented):**
  yes, this deserves the same treatment as the pre-existing HITL-tool-ownership
  collision a few lines below (`Tool '{name}' has HitlSpec declarations from
  two capabilities...`). Both capabilities' contexts are already in hand
  inside this one function, so the check is free to add and there is a direct
  precedent to mirror. Implemented: a `tool_owner: dict[str, str]` tracks which
  capability first claimed each tool name; a second, *different* capability
  claiming the same name raises `CapabilityAssemblyError` naming both
  capabilities and the tool — never silently shadows. (Two tools of the same
  name from the *same* capability are not specially handled — last one wins in
  the dict — this was not asked for and isn't a cross-capability collision.)

- **Collision decision 2 — capability tool name vs. MCP-resolved runtime tool
  name (deferred to Phase 4, NOT implemented here):** investigated per the
  instructions before writing anything. `assembly.py` / `build_capability_agent_block`
  has zero visibility into MCP-resolved tool names — `_active_mcp_server_refs`,
  `FredMcpToolProvider`, and `services.tool_invoker`/`ToolInvokerPort` all live
  in `agent_app.py` only (grepped; zero hits in `capabilities/`). `McpCapability`
  itself (`capabilities/mcp.py`) never overrides `tools()` and its `middleware()`
  override carries only a prompt-fragment middleware with no `.tools` — it is
  not a tool source at assembly time at all; the actual MCP tool objects are
  loaded later, in `agent_app.py`, through `FredMcpToolProvider`, a completely
  separate code path from this module. There is no data this function could
  read to perform this check without plumbing MCP tool names in from outside
  purely to satisfy this one check — exactly the "guessing / forcing in
  unrelated data" the task said to avoid. **Deferred to Phase 4**, the first
  point where `GraphRuntime` actually merges `capability_block.tools` with the
  runtime's other tool sources — both sides of the potential collision are
  finally in scope together there. Flagging explicitly rather than silently
  dropping it, per instructions.

Tests: `libs/fred-runtime/tests/test_capability_agent_1973.py` — added a
`block.tools` section (3 new tests: tools collected/deduped across
capabilities, `block.hitl[...].tool` is literally the same object as in
`block.tools`, cross-capability same-name collision raises
`CapabilityAssemblyError`). The pre-existing `_GadgetCapability` fixture (HITL
tracer) was migrated from a hand-rolled `middleware()` override carrying
`self.tools = [...]` to implementing `tools()` directly — under the new
source-of-truth rule this was required for its own test
(`test_hitl_when_predicate_sees_typed_context_and_real_args`, which asserts
`request.tool is not None`) to keep passing, and it's the correct migration
per the tools()-primary contract anyway (this capability has no ReAct-only
hook, so it never needed `middleware()` at all). No changes needed to
`test_capability_selection_1974.py` or `test_capability_document_access_1906.py`
— both assert on `block.middleware[...].tools`, untouched by this refactor.

**Open TODO, not yet resolved — flagged per developer request (2026-07-22):**
`fred_runtime/capabilities/demo.py` (`DemoEchoCapability`) still overrides
`middleware()` directly instead of implementing `tools()` — it predates
Phase 1 and was out of scope to touch in Phase 2 (not `assembly.py`, not a
test). Confirmed by reading the full module: it is the in-tree
reference/tracer capability for the capability system itself (its own
docstring: "the minimal in-tree tracer... test/in-code enablement only — no
product surface yet"), not something registered on any production pod via a
`fred.capabilities` entry point today — so the immediate blast radius is low.
That said, this was NOT verified with the same rigor as `document_access`
(no dedicated test, no empirical check), so treat "harmless today" as an
untested assumption, not a settled fact. Its tool is invisible to
`CapabilityAgentBlock.tools` as things stand (it declares no `hitl_specs`,
so nothing currently reads it through that field either).
**Action needed before this bridge is considered complete for the general
case (not just `document_access`):** migrate `DemoEchoCapability` to
`tools()` the same way Phase 1 migrated `document_access`, specifically
because it's the reference implementation every future capability author
copies — leaving it on the old pattern signals the wrong convention by
example. Do this as part of Phase 6 (end-to-end proof) or as an explicit
follow-up immediately after; do not close out this NOTES file with it still
pending.

Validation: `cd libs/fred-runtime && make code-quality && make test` — both
green, 583 tests passed (up from 569 pre-Phase-1-merge baseline + 14 new/moved
in this file), zero regressions, no other test file needed changes.

### Phase 3 — remove the two ReAct-only gates — DONE (2026-07-22)
File: `libs/fred-runtime/fred_runtime/app/agent_app.py`
- `_effective_capability_ids` (~line 2234): dropped the
  `isinstance(definition, ReActAgentDefinition)` early return — it now
  resolves identically for `ReActAgentDefinition` and `GraphAgentDefinition`.
  Docstring's stale "Non-ReAct templates carry no capabilities" sentence
  replaced with "Resolved identically for ReAct and Graph agents."
- `_build_capability_block` (~line 2318): dropped the `CapabilityError`-raising
  branch entirely (the `isinstance` check plus its
  `"Capabilities are only supported on ReAct agents (RFC §5)..."` raise and
  early `return None`). The block is now built **uniformly** for both agent
  kinds — no agent-kind branching left in this function at all. Docstring
  updated to say so; the unrelated RFC §3.9 "never silently degrade"
  paragraph (why a broken capability still raises loudly) was left untouched
  as instructed — that principle is orthogonal to the gate removed here.
- `_enforce_turn_options` (~line 2278, the pre-stream 422 gate): read, not
  changed. It was already generic — it just forwards to
  `_effective_capability_ids` and `validate_turn_options` with no
  `isinstance`/agent-kind branch of its own — so fixing
  `_effective_capability_ids` alone was sufficient; a Graph agent's
  `turn_options` for a capability it legitimately selected now validates the
  same way a ReAct agent's would, no code change needed.
- Broader search (step 4): grepped `ReAct`, `CapabilityError`,
  `isinstance.*ReActAgentDefinition` across the whole file. Two other
  `isinstance(definition, ReActAgentDefinition)` sites remain
  (`_bind_binding_and_services`'s `build_authored_tool_handlers` gate at
  ~line 772, and `_apply_runtime_tuning`'s `system_prompt_template` overlay at
  ~line 1075) — both read and confirmed **unrelated** to the
  `AgentCapability`/capability-block system this phase touches (they gate
  the separate `declared_tool_refs`/authored-tools and prompt-overlay
  mechanisms, which stay legitimately ReAct-only and are out of this NOTES
  file's scope). Left untouched. No stale comment, dead branch, or test mock
  assuming "Graph agents never have capabilities" was found anywhere else.
- Tests: no existing test asserted the old raise-on-non-ReAct behavior (grepped
  `CapabilityError`, `_effective_capability_ids`, `only supported on ReAct`,
  `GraphAgentDefinition` across `tests/` — zero hits combining a Graph
  definition with a capability selection; the two direct `_build_capability_block`
  tests in `test_agent_app.py` only exercise the MCP/ReAct lane and needed no
  changes). Added
  `test_build_capability_block_for_graph_agent_returns_tools` in
  `libs/fred-runtime/tests/test_agent_app.py` — a minimal `GraphAgentDefinition`
  (modeled on `fred-sdk`'s `_ConvAgent`/`_PlainAgent` test fixtures) plus a
  minimal `tools()`-only capability, proving `_build_capability_block` returns
  a `CapabilityAgentBlock` with the capability's tool in `.tools`, no error.
- Validation: `cd libs/fred-runtime && make code-quality && make test` — both
  green, 584 tests passed (583 Phase-2 baseline + 1 new), zero regressions.
- End state confirmed exactly as scoped: a Graph agent can now select
  capabilities and `_build_capability_block` returns a real, non-empty block
  for it — but the one `GraphRuntime(...)` call site (~line 2551) still does
  not accept or pass a `capability_block=` kwarg, so nothing yet reads
  `.tools` on the Graph execution path. Graph capability selection is
  correctly-built but inert until Phase 4. No stopgap wiring was added.
- Nothing here changes the Phase 4-6 plan below — the deferred MCP-name-vs-
  capability-name collision check and the plain-dict-invocation adapter
  problem (both flagged at the end of Phase 1/2) remain exactly where they
  were, still Phase 4's job.

### Phase 4 — `GraphRuntime` consumes `capability_block.tools` — DONE (2026-07-22)
File: `libs/fred-runtime/fred_runtime/graph/graph_runtime.py`

- `GraphRuntime.__init__` gains `capability_block: CapabilityAgentBlock | None
  = None` (imported from `fred_runtime.capabilities.assembly`, mirroring
  `ReActRuntime.__init__`'s existing parameter exactly — same name, same
  `self._capability_block` storage). `build_executor` now builds
  `mcp_tools` (unchanged, from `services.tool_provider.get_tools()`) and
  `capability_tools = _adapted_capability_tools(self._capability_block,
  mcp_tool_names={t.name for t in mcp_tools})`, and passes
  `runtime_tools=mcp_tools + capability_tools` into
  `_DeterministicGraphExecutor` — unchanged itself, exactly as scoped (it
  already just does `{tool.name: tool for tool in runtime_tools}`).

**The adapter — investigated empirically, not assumed.** Confirmed
`langchain-core==1.4.9` (this repo's pin, `>=0.3.0` in `pyproject.toml`) via a
throwaway introspection script against a real `document_access` tool
instance: `StructuredTool` (what `@tool` produces) exposes its underlying
async function directly on `.coroutine` — a plain `Callable[..., Awaitable]`
taking the tool's own keyword arguments (`question=...`), NOT the single-dict
signature `.ainvoke()` uses. Calling `.coroutine(**kwargs)` directly returns
the function body's real Python return value with zero interference from
`BaseTool.ainvoke()`'s response-shape handling — for
`document_access`'s tool, the genuine `(content_str, ToolInvocationResult)`
2-tuple, confirmed by direct invocation in the same script.

Landed on `_adapt_capability_tool_for_graph(source_tool: BaseTool) ->
BaseTool` (`graph_runtime.py`, next to `GraphRuntime`): reads
`getattr(source_tool, "coroutine", None)` (plain `BaseTool` doesn't type this
attribute — `getattr` avoids a basedpyright error without a defensive branch
that can actually fire for today's capability tools), builds a new
`StructuredTool.from_function(name=..., description=..., args_schema=...,
coroutine=_invoke)` where `_invoke` awaits the original coroutine and, if the
result is a 2-tuple, returns only its second element (the artifact) —
otherwise passes the raw result through unchanged (covers a capability tool
that already returns a bare `ToolInvocationResult`, matching Phase 1's other
proven-safe shape). The wrapper's own `response_format` is left at
LangChain's default (`"content"`) deliberately — that is the shape Phase 1
proved survives a plain-dict `.ainvoke()` intact. No new tool class, no
config knob, ~15 lines. `document_access`'s tool definition is untouched;
the adaptation lives entirely at this merge seam (RFC invariant B holds).

Considered and rejected: reusing `react_tool_resolution._resolve_runtime_provider_tool`'s
three-way return-shape handling as the template, per the task's suggestion —
checked it first. Its `_invoke` still calls `runtime_tool.ainvoke(payload)`
(not the underlying coroutine), so for a `content_and_artifact` tool it hits
the exact same collapse Phase 1 found: the 2-tuple branch it contains is
unreachable for this tool shape, just like `_normalize_runtime_tool_output`'s
own dead branch noted in Phase 1. Not reusable for this problem — the fix
had to bypass `.ainvoke()` entirely, which is a materially different
mechanism, not a copy of that function.

**Empirical proof test** (`tests/test_graph_capability_bridge.py`):
`test_adapted_capability_tool_sources_survive_invoke_runtime_tool` builds
`document_access`'s real tool, adapts it with `_adapt_capability_tool_for_graph`
exactly as `build_executor` does, registers it on a real
`_GraphNodeExecutionContext` (the concrete class `GraphNodeContext` is at
runtime — same harness pattern as the pre-existing
`test_graph_runtime_invoke_agent.py`), and calls its real, unmocked
`invoke_runtime_tool("search_documents_using_vectorization", {"question":
...})`. Result: a dict (`_normalize_runtime_tool_output` `model_dump`s the
bare `ToolInvocationResult` — no special-cased handling for it exists, and
none was needed) with `result["sources"][0]["uid"] == "d1"` intact. A sibling
control test, `test_unadapted_capability_tool_loses_sources_via_invoke_runtime_tool`,
registers the RAW (unadapted) tool through the same real path and asserts
`"sources" not in result` — reproducing Phase 1's finding through the actual
production code path and proving the adapter is load-bearing, not a no-op.
A third unit test, `test_adapt_preserves_bare_tool_invocation_result_tools_unchanged`,
covers the other proven-safe shape (bare `ToolInvocationResult`, no
`response_format`) round-tripping through the adapter unchanged.

**MCP-vs-capability collision (resolved here, deferred from Phase 2):**
`_adapted_capability_tools(capability_block, *, mcp_tool_names: set[str])`
raises `CapabilityAssemblyError` (imported from
`fred_runtime.capabilities.errors`, same class the Phase 2 cross-capability
collision uses — no new error type) naming the tool the moment a capability
tool's name is already present in `mcp_tool_names`, before any adaptation
happens. `build_executor` computes `mcp_tool_names` from the same
`mcp_tools` tuple it already builds from `tool_provider.get_tools()`, so both
sides of the collision (capability tool names, MCP-resolved runtime tool
names) are finally in scope together, exactly where Phase 2 said they would
be. Tests: `test_capability_tool_colliding_with_mcp_tool_name_raises` and
`test_capability_tools_merge_cleanly_when_no_mcp_name_collision` exercise
`_adapted_capability_tools` directly; `test_build_executor_raises_on_capability_mcp_name_collision`
and `test_build_executor_merges_mcp_and_adapted_capability_tools` exercise
the full `GraphRuntime.build_executor` wiring (fake `ToolProviderPort` +
real `CapabilityAgentBlock` + a minimal `GraphAgentDefinition` fixture
modeled on `test_agent_app.py`'s), proving the merged executor's
`_runtime_tools` carries both tool sources by name, and that the capability
tool actually registered on the executor is the adapted wrapper (asserted via
`response_format == "content"`, not the raw tool's `"content_and_artifact"`).

Tests: `libs/fred-runtime/tests/test_graph_capability_bridge.py` (new file,
8 tests). Validation: `cd libs/fred-runtime && make code-quality && make
test` — both green, 592 tests passed (584 Phase-3 baseline + 8 new), zero
regressions.

End state: a Graph agent that selects capabilities now gets their tools
merged into `runtime_tools`, invocable via `invoke_runtime_tool` with full
`ToolInvocationResult` fidelity (sources, blocks), and a capability tool name
colliding with an MCP-resolved tool name fails loudly at executor build time
instead of silently shadowing. `GraphRuntime` itself still isn't
constructed with `capability_block=` anywhere — the one call site in
`agent_app.py` (~line 2551) is untouched, exactly as scoped; that's Phase 5.

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
changes).

Phase 2 implemented and verified (2026-07-22): `libs/fred-runtime` passes
`make code-quality && make test` (583 tests, zero regressions). See the Phase 2
section above for the collision-handling decisions (cross-capability tool-name
collision implemented; capability-vs-MCP collision explicitly deferred to
Phase 4, not silently dropped) and the `DemoEchoCapability` migration note for
whoever picks up later phases.

Phase 3 implemented and verified (2026-07-22): `libs/fred-runtime` passes
`make code-quality && make test` (584 tests, zero regressions). The two
ReAct-only gates in `agent_app.py` (`_effective_capability_ids`,
`_build_capability_block`) are gone; `_enforce_turn_options` needed no change
(already generic). End state: a Graph agent can select capabilities and get a
real, non-empty `CapabilityAgentBlock` built for it, but the one
`GraphRuntime(...)` call site still doesn't accept or pass
`capability_block=` — nothing reads `.tools` on the Graph path yet. That is
exactly Phase 4's job, left untouched here. Phases 4-6 not started.

Phase 4 implemented and verified (2026-07-22): `libs/fred-runtime` passes
`make code-quality && make test` (592 tests, zero regressions). The Phase
1 plain-dict-invocation problem is resolved at the merge seam (not by
touching `document_access`'s tool) via `_adapt_capability_tool_for_graph`,
proven empirically against the real `invoke_runtime_tool` path (see the
Phase 4 section above for the adapter mechanism and the control test that
reproduces Phase 1's bug when the adapter is skipped). The Phase 2
capability-vs-MCP tool-name collision deferral is also resolved here
(`_adapted_capability_tools`, raises `CapabilityAssemblyError`). `GraphRuntime`
now accepts and stores `capability_block`; `build_executor` merges adapted
capability tools into `runtime_tools`. Nothing outside
`graph_runtime.py`/its tests was touched — `agent_app.py`'s one
`GraphRuntime(...)` call site still doesn't pass `capability_block=`.

Next action: Phase 5 (wire `capability_block=capability_block` into the one
`GraphRuntime(...)` construction call in `agent_app.py`, ~line 2551 — the
`capability_block` local is already computed above that call for the ReAct
branch, per Phase 3's end-state note). No known open design questions remain
for Phase 5 — Phase 4 closed the last one (plain-dict-invocation adapter +
MCP-collision) flagged by earlier phases. Phase 6 (end-to-end proof agent
scenario) still has its `DemoEchoCapability` migration TODO pending, flagged
in the Phase 2 section above.
