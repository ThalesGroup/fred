# Multi-Agent Conversational Memory — Implementation Backlog

**RFC**: [`docs/rfc/MULTI-AGENT-MEMORY-RFC.md`](../rfc/MULTI-AGENT-MEMORY-RFC.md)

**Status**: Core implementation landed (2026-05-05) — post-implementation hardening pending before final closeout

**Why this track exists**: Graph agents (including `TeamAgent`) are stateless across turns. A user's second question fails to route correctly and reaches the sub-agent without any knowledge of the prior exchange. The RFC defines the fix as a general SDK contract, not a TeamAgent-specific patch. This backlog tracks implementation in phases.

---

## Phase A — SDK Primitives (`fred-sdk`)

These are the foundational types and contracts. Nothing else can start until A is done.

### A.0 Convergence rule for this track

- [x] Treat the memory work as a convergence opportunity, not a patch lane:
  do not introduce additional request/context shapes just to carry history
- [x] Before adding new fields, inspect whether the touched runtime path can
  shrink or retire one transitional bridge in the same change
- [x] If `_AgentExecuteRequest` cannot be removed yet, keep a single projection
  boundary and do not spread new feature logic across both public and private
  models without documenting why

### A.1 Shared types

- [x] Add `ConversationTurn(user_message, agent_response, agent_name?)` to `fred_sdk.contracts.context` (placed in `context.py` to avoid circular imports with `models.py`)
- [x] Add `ConversationalState(conversation_history: tuple[ConversationTurn, ...] = ())` mixin to `fred_sdk.contracts.context`
- [x] Export both from `fred_sdk.contracts.__init__` (or equivalent public surface)
- [x] Unit tests: model construction, serialisation round-trip, immutability (frozen)

### A.2 `GraphAgentDefinition` contract extension

- [x] Add `_turn_carry_fields() -> frozenset[str]` hook to `GraphAgentDefinition`
- [x] Add `conversation_history_max_turns: ClassVar[int] = 20` to `GraphAgentDefinition`
- [x] Change `build_turn_state` default to carry forward only explicit carry fields
- [x] Extend `build_turn_state(..., invocation_turns=())` so invoked graph agents can seed history on first use
- [x] Enforce depth limit during carry-forward and invocation seeding
- [x] Unit tests:
  - carry-forward when `previous_state` is `None` → same as `build_initial_state`
  - carry-forward when state includes `ConversationalState` → history carried
  - carry-forward when state does NOT include `ConversationalState` → no change in behaviour
  - invocation seeding when `previous_state is None` and `invocation_turns` is non-empty
  - depth limit: history truncates to last N turns oldest-first

### A.3 History append — `build_completed_state` hook

- [x] Add `build_completed_state(state) -> state` hook to `GraphAgentDefinition` with identity default
- [x] Ensure runtime persists the completed state before building output
- [x] Unit tests: output round-trip, state after completion includes new turn

### A.4 `AgentInvocationRequest` extension

- [x] Add `prior_turns: tuple[ConversationTurn, ...] = ()` to `AgentInvocationRequest` in `fred_sdk.contracts.context`
- [x] Add `prior_turns: tuple[ConversationTurn, ...] = ()` keyword argument to `GraphNodeContext.invoke_agent` in `fred_sdk.graph.runtime`
- [x] Add `invocation_turns: tuple[ConversationTurn, ...] = ()` to `ExecutionConfig`
- [x] Ensure the default remains empty so all existing callers are unaffected
- [x] Unit tests: request and execution-config serialisation with and without `prior_turns`

---

## Phase B — `TeamAgent` consumes the primitives (`fred-sdk`)

`TeamAgent` must use the general primitives from Phase A — not re-implement them.

### B.1 `TeamState` includes `ConversationalState`

- [x] Update the shared `TeamState` class to inherit from `ConversationalState`
- [x] Keep `TeamAgent.__pydantic_init_subclass__` assigning `state_schema = TeamState`
- [x] Verify that `conversation_history` carries forward on turn 2 without any author override

### B.2 History append for `TeamAgent`

- [x] Auto-generate `build_completed_state` in `TeamAgent.__pydantic_init_subclass__` to append `ConversationTurn(user_message=state.user_message, agent_response=state.final_text, agent_name=<last member name>)` after each turn
- [x] Determine "last member name" from `state.results[-1].agent_name` when results are non-empty; use `None` otherwise

### B.3 Coordinator prompt enrichment

- [x] Add `_format_conversation_history(history: tuple[ConversationTurn, ...]) -> str` helper in `team_api.py`
- [x] Update `_make_member_step` to include history block in inline member prompts when `state.conversation_history` is non-empty
- [x] Update `_make_route_coordinator_step` to include history block in the prompt when `state.conversation_history` is non-empty
- [x] Update `_make_coordinator_step` (dynamic mode) to include history block in the prompt when `state.conversation_history` is non-empty
- [x] Unit tests:
  - member step with history → history block present
  - route coordinator with empty history → prompt unchanged (no regression)
  - route coordinator with non-empty history → history block present in prompt
  - dynamic coordinator with history → history block present

### B.4 `_make_agent_invoke_step` passes `prior_turns`

- [x] In `_make_agent_invoke_step`, pass `state.conversation_history` as `prior_turns` to `context.invoke_agent`
- [x] Pass the empty tuple on first turn — no change in behaviour for first-turn invocations
- [x] Unit tests: `invoke_agent` called with correct `prior_turns` on turn 2

---

## Phase C — Runtime enforcement (`fred-runtime`)

### C.0 Preliminary execution-seam convergence

- [x] Route `LocalRegistryAgentInvoker.invoke(...)` through `RuntimeExecuteRequest` before `_AgentExecuteRequest`
- [x] Extract runtime setup from `_iterate_runtime_event_payloads(...)` into one typed preparation path so future continuity fields land once
- [x] Keep `_AgentExecuteRequest` as the single remaining private projection boundary; do not add memory-specific plumbing on both sides
- [x] Offline validation: `make code-quality` and `make test` in `libs/fred-runtime` (2026-05-05)

### C.1 ReAct agent context injection

- [x] In `ReActRuntime`, detect when `ExecutionConfig.invocation_turns` is non-empty
- [x] Render `invocation_turns` with the shared formatter
- [x] Inject the rendered context block as a leading `SystemMessage` prepended to the input messages (rather than appended to system prompt, since the system prompt is baked at compile time in the cached executor)
- [x] Injection is transparent to the agent author — no `system_prompt_template` change is needed
- [x] Unit tests:
  - ReAct agent invoked without `invocation_turns` → system prompt unchanged
  - ReAct agent invoked with `invocation_turns` → context block appended
  - Context block does not duplicate the current `message`

### C.2 In-process invoker forwards `prior_turns`

- [x] Update `LocalRegistryAgentInvoker.invoke` to forward `prior_turns` into the callee execution path
- [x] Ensure the internal execution bridge preserves `prior_turns` when calling `_iterate_runtime_event_payloads`
- [x] Unit tests: in-process agent invocation with and without `prior_turns`

### C.3 Remote invoker forwards `prior_turns`

- [x] Update `RemoteSseAgentInvoker.invoke` to include `prior_turns` in the HTTP payload
- [x] Extend the runtime execute bridge so `prior_turns` reaches the callee without introducing a second public execution API
- [x] Prefer converging the remote path on `RuntimeExecuteRequest` / typed execution plumbing rather than deepening `to_legacy_context()` usage
- [x] Unit tests: payload construction with and without `prior_turns`

### C.4 Graph agent runtime — verify `build_completed_state` and `invocation_turns` are used

- [x] In `GraphRuntime`, pass `ExecutionConfig.invocation_turns` into `build_turn_state`
- [x] In `GraphRuntime._execute_loop`, call `build_completed_state` after the terminal node completes and before persisting the final checkpoint
- [x] Unit tests:
  - after a two-turn graph agent execution, the checkpointer holds state with `conversation_history` length 2
  - invoked graph callee with no prior state receives seeded history from `invocation_turns`

---

## Phase D — Integration validation

- [x] Write an integration scenario: unit tests in `fred-sdk/tests/test_conversational_memory.py` and `fred-runtime/tests/test_conversational_memory.py` covering all A–C backlog items offline
- [x] Manual validation: `fred.samples.team_of_3.router` — "what is 4+4?" → "multiply it by 3" → "and again by 3" all routed to `fred.samples.team_of_3.react_math`; final answer 72 = 24×3 confirmed (2026-05-05)
- [x] Confirm all existing `fred-sdk` tests pass (103 tests, A.2 default-behaviour guard passes)
- [x] Confirm all existing `fred-runtime` tests pass (150 tests)
- [x] `make code-quality && make test` pass in both `fred-sdk` and `fred-runtime` (2026-05-05)

---

## Phase E — Documentation

- [x] Update `docs/rfc/MULTI-AGENT-MEMORY-RFC.md` status from `Draft` to `Implemented` (2026-05-05)
- [x] Update `docs/authoring/AGENTS.md` with a multi-turn section explaining `ConversationalState`, `build_turn_state` override, and depth limits (2026-05-05)
- [x] Add `ConversationTurn` and `ConversationalState` pointer to `docs/platform/V2_AGENT_CREATION.md` (2026-05-05)
- [x] Update `docs/WORKPLAN.md` task status (2026-05-05)

---

## Phase F — Post-Implementation Hardening

These follow-up slices should be implemented as separate small branches from
`swift`. They are not new scope; they are the minimum cleanup needed to make
the memory implementation match the RFC's "reduce, do not grow" rule.

### F.1 Agent-scoped checkpoint isolation

- [ ] Isolate persisted graph/ReAct state per agent within a shared `session_id`
- [ ] Do not let multiple agents in the same conversation load or overwrite each other's completed or pending checkpoints
- [ ] Use one consistent strategy across GraphRuntime and ReActRuntime
- [ ] Preserve HITL resume semantics while introducing the agent-scoped key/namespace
- [ ] Regression tests:
  - two different graph agents sharing one `session_id` do not share completed state
  - a TeamAgent and a callee agent sharing one `session_id` do not bleed memory into each other
  - resume still works when checkpoint isolation is enabled
- [ ] Suggested branch: `fix/memory-agent-checkpoint-isolation`

### F.2 Remote execute-contract convergence

- [ ] Make `RemoteSseAgentInvoker` send the public `RuntimeExecuteRequest` shape (`input`, `runtime_context`, `invocation_turns`) instead of legacy `message` / `context`
- [ ] Keep the remote agent-to-agent path on the same typed transport shape as pod-local and HTTP execution
- [ ] Do not introduce a second remote payload contract just for memory
- [ ] Regression tests:
  - remote invoker payload matches `RuntimeExecuteRequest`
  - invocation turns still propagate to remote callees
- [ ] Suggested branch: `fix/remote-agent-runtime-execute-contract`

### F.3 Local execution-seam convergence

- [ ] Remove the duplicate hand-built `_AgentExecuteRequest` construction in `LocalRegistryAgentInvoker`
- [ ] Reuse `_to_internal_request(RuntimeExecuteRequest)` or its direct successor so local and HTTP execution share one projection path
- [ ] Keep `_AgentExecuteRequest` as a single temporary boundary until it can be removed entirely
- [ ] Regression tests:
  - local invoker continues to preserve `prior_turns`
  - no drift between local and HTTP request projection for execution metadata
- [ ] Suggested branch: `refactor/local-agent-execute-projection`

### F.4 Team history cap enforcement

- [ ] Enforce `conversation_history_max_turns` when `TeamAgent.build_completed_state` appends the new turn
- [ ] Keep persisted state aligned with the same oldest-first truncation rule used by `build_turn_state`
- [ ] Regression tests:
  - appending at `max_turns` keeps exactly `max_turns`
  - oldest turn is discarded first
- [ ] Suggested branch: `fix/team-memory-history-cap`

### Recommended branch order

1. `fix/memory-agent-checkpoint-isolation`
2. `fix/remote-agent-runtime-execute-contract`
3. `refactor/local-agent-execute-projection`
4. `fix/team-memory-history-cap`

---

## Resolved Decisions

| Decision | Chosen answer |
|---|---|
| Carry policy | Explicit `_turn_carry_fields()`; do not carry arbitrary overlapping state fields |
| Invoke boundary type | Typed `prior_turns: tuple[ConversationTurn, ...]` |
| History limit placement | `conversation_history_max_turns` on `GraphAgentDefinition` |
| History append hook | `build_completed_state(state)` before persistence and output building |
| Invoked callee scope | Support both ReAct and graph callees in the first implementation |
| Runtime-plumbing strategy | Use the memory change to shrink transitional execution bridges where touched |

---

## Progress

| Phase | Status | Notes |
|---|---|---|
| RFC | Implemented (2026-05-05) | Design accepted; hardening follow-ups tracked below |
| A – SDK primitives | Complete (2026-05-05) | `ConversationTurn`, `ConversationalState` in `context.py`; `build_turn_state` carry-forward + `build_completed_state` in `models.py`; all contract extensions done; 103 tests pass |
| B – TeamAgent | Complete (2026-05-05) | `TeamState` inherits `ConversationalState`; auto-generated `build_completed_state`; all three prompt helpers enriched; `prior_turns` forwarded in `_make_agent_invoke_step` |
| C – Runtime | Implemented with hardening pending | Core continuity path works; follow-up runtime convergence and checkpoint-isolation slices remain |
| D – Integration | Complete (2026-05-05) | 28 new offline tests across `fred-sdk` + `fred-runtime`; manual 3-turn validation with `fred.samples.team_of_3.router` confirmed correct routing and arithmetic through 3 turns |
| E – Docs | Complete (2026-05-05) | RFC status updated; `AGENTS.md` multi-turn section added; `V2_AGENT_CREATION.md` pointer added; `WORKPLAN.md` updated |
| F – Hardening | Planned | Split into four branchable follow-up slices from `swift` |
