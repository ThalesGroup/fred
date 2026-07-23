# NOTES — Graph agents ↔ AgentCapability bridge

**Status: superseded as design source (2026-07-23).** This branch's work is complete
and now documented as the platform's actual state in
`docs/swift/rfc/AGENT-CAPABILITY-RFC.md` §3.2/§3.9/§5.1 (design),
`docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md` §8.22 (implementation record), and
`docs/swift/capabilities/AUTHORING.md` (authoring guidance) — read those first. This
file stays only as the compact implementation log a handful of docstrings point to by
phase number (`graph_runtime.py`, `document_access/capability.py`, `test_agent_app.py`,
`test_graph_capability_bridge.py`, `test_test_assistant_document_scenario.py`,
`graph_agent.py`, `graph_steps.py`).

## The problem this closed

`AgentCapability` was ReAct-only: `middleware()` was its only runtime hook, consumed
solely by `create_agent()`. A `GraphAgentDefinition` selecting a real (non-MCP)
capability failed loudly with `CapabilityError`. `McpCapability` was unaffected — its
tools load through `FredMcpToolProvider`, a path already shared by both runtimes.

## Design invariants

- **Graph SDK stays untouched.** `fred_sdk/graph/*` gets zero new imports, zero new
  concepts — a Graph author never learns "capability" exists.
- **The contract is redesigned, not patched.** `AgentCapability.tools()` becomes the
  primary, execution-model-agnostic authoring surface; `middleware()` becomes the
  ReAct-only escape hatch with a generic default built from `tools()`.

## Phase log

**Phase 1 — `fred-sdk` contract change.** Added `tools()` to `AgentCapability`
(default `()`); `middleware()` lost `@abstractmethod`, defaults to wrapping `tools()`.
Migrated `document_access` onto `tools()`. **Empirical finding, load-bearing for Phase
4:** a `content_and_artifact` tool's `ToolInvocationResult` artifact survives a real
`ToolCall`-dict invocation (`create_agent()`'s path) but is silently dropped by a
plain-dict `.ainvoke()` (`invoke_runtime_tool`'s path) — LangChain returns a bare
content string, not even a 2-tuple. No single return convention is correct on both
paths; `document_access` kept `content_and_artifact` (correct for its only path today),
deferring the plain-dict survival problem to the merge seam, not the tool's own shape.

**Phase 2 — `CapabilityAgentBlock.tools`.** Added a `tools` field, built directly from
`capability.tools(ctx)` per selected capability, deduped by name; a cross-capability
name collision raises `CapabilityAssemblyError`. `demo.py`'s TODO (still
`middleware()`-only) flagged, resolved in Phase 6.

**Phase 3 — removed the two ReAct-only gates** in `agent_app.py`
(`_effective_capability_ids`, `_build_capability_block`) — the block now builds
identically for both agent kinds. `GraphRuntime` still didn't consume it yet.

**Phase 4 — `GraphRuntime` consumes `capability_block.tools`.** Built
`_adapt_capability_tool_for_graph`: reads the source tool's `.coroutine` directly
(bypassing `.ainvoke()`'s response-shape handling), and if the result is a 2-tuple
returns only the artifact — the one shape Phase 1 proved survives a plain-dict
`.ainvoke()` intact. Proven against the real `document_access` tool through the real
`invoke_runtime_tool` path, with a control test reproducing the artifact-loss bug when
the adapter is skipped. Also resolves the Phase-2-deferred capability-vs-MCP tool-name
collision (`_adapted_capability_tools`, same `CapabilityAssemblyError`).

**Phase 5 — wired `capability_block=` into the one `GraphRuntime(...)` call site**
(`agent_app.py`). One-line change; the block was already computed identically for both
agent kinds since Phase 3.

**Phase 6 — end-to-end proof.** `test_assistant` gained a `document` scenario (search →
HITL confirm/discard → branch) on a real `GraphRuntime` + `CapabilityAgentBlock`,
including the graceful-failure path when the capability isn't selected. `demo.py`
migrated onto `tools()`, closing the Phase 2 TODO.

## Validation against real external agents

`dt-agents/aegis`, `dt-agents/dva_risk_validator_team`, `fred-samples/cvem_watch` — read
in full to check the plan against reality. None use package capabilities; all run on
`McpCapability`/`default_mcp_servers` or the separate `declared_tool_refs`/`invoke_tool`
lane, both already execution-model-agnostic and untouched by this work. Zero regression
risk confirmed; the bridge is strictly additive.

## Three corrections (2026-07-23, CAPAB-02)

Three rounds of independent review, each verified against the code before fixing, found
real gaps in the landing above. See `docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md`
§8.23–§8.25 and `id-legend.yaml`'s `CAPAB-02` entry for the full record. This file is
not updated further — those and the RFC are now the canonical source.

**Round 1 (§8.23):** nothing stopped a Graph agent from *selecting*
`ppt_filler`/`writable_document` (`middleware()`-only) — it would build without error and
silently get zero tools. Fixed with `CapabilityManifest.execution_models`, a loud
`CapabilityError` at assembly. Also fixed: `document_access`'s tree/summarize artifacts
carried no payload; `tools(ctx)` called twice per assembly; `demo.py`'s tool was sync.

**Round 2 (§8.24):** round 1's single-call fix made `tools()` and an overridden
`middleware()` either/or instead of composed (fixed); the capability catalog still
offered ReAct-only capabilities to Graph templates (now filtered); a capability with an
active `HitlSpec` selected on Graph now fails loudly instead of running ungated
(stopgap); `document_access`'s FAILURE-path artifacts also carried no payload (fixed);
`invoke_runtime_tool` misreported `is_error` on its trace event (fixed); the adapter now
refuses a sync `content_and_artifact` tool loudly instead of silently breaking, and its
tuple-unwrap is gated on `response_format`; `McpCapability`'s prompt-fragment gap is
documented, not fixed (no Graph-side prompt-injection mechanism exists).

**Round 3 (§8.25):** round 1's `execution_models` fix only caught a capability that
EXPLICITLY declared itself ReAct-only — an author who just forgot to mention the field
kept the class default (both models) and still shipped a silent Graph no-op. Fixed with
a BOOT invariant (`UndeclaredExecutionModelError`, via `model_fields_set`), not another
runtime check — a `middleware()`-only capability that never declared `execution_models`
now fails pod startup, not just Graph assembly. `CapabilityManifest` also now requires
`"react"` always be present. Also fixed: `document_access`'s 403/404 recovery hint was
appended to the message after the artifact was already built (so it never reached the
artifact); `invoke_runtime_tool` read `is_error` off the normalized dict, not the typed
`ToolInvocationResult` (risked misclassifying an unrelated tool's own field), and never
populated `sources`/`ui_parts` on its event at all.

## Still open (not fixed here, not a regression)

- Full Graph HITL support: `CapabilityAgentBlock.hitl` is never consulted by
  `GraphRuntime` (round 2 added a loud refusal as a stopgap, not the real thing) —
  reconciling Graph's own node-level pause/resume with the per-tool gate is a separate
  design task.
- Whether a capability's ReAct-only `middleware()` contributions (prompt fragments,
  dynamic schemas) should ever become expressible to Graph agents is an open question,
  not a bug — `execution_models=("react",)` is a deliberate, declared boundary today.
