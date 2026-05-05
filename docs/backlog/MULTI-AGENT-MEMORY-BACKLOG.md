# Multi-Agent Conversational Memory — Implementation Backlog

**RFC**: [`docs/rfc/MULTI-AGENT-MEMORY-RFC.md`](../rfc/MULTI-AGENT-MEMORY-RFC.md)

**Status**: Implementation started — runtime convergence slice complete (2026-05-05)

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

- [ ] Add `ConversationTurn(user_message, agent_response, agent_name?)` to `fred_sdk.contracts.models`
- [ ] Add `ConversationalState(conversation_history: tuple[ConversationTurn, ...] = ())` mixin to `fred_sdk.contracts.models`
- [ ] Export both from `fred_sdk.contracts.__init__` (or equivalent public surface)
- [ ] Unit tests: model construction, serialisation round-trip, immutability (frozen)

### A.2 `GraphAgentDefinition` contract extension

- [ ] Add `_turn_carry_fields() -> frozenset[str]` hook to `GraphAgentDefinition`
- [ ] Add `conversation_history_max_turns: ClassVar[int] = 20` to `GraphAgentDefinition`
- [ ] Change `build_turn_state` default to carry forward only explicit carry fields
- [ ] Extend `build_turn_state(..., invocation_turns=())` so invoked graph agents can seed history on first use
- [ ] Enforce depth limit during carry-forward and invocation seeding
- [ ] Unit tests:
  - carry-forward when `previous_state` is `None` → same as `build_initial_state`
  - carry-forward when state includes `ConversationalState` → history carried
  - carry-forward when state does NOT include `ConversationalState` → no change in behaviour
  - invocation seeding when `previous_state is None` and `invocation_turns` is non-empty
  - depth limit: history truncates to last N turns oldest-first

### A.3 History append — `build_completed_state` hook

- [ ] Add `build_completed_state(state) -> state` hook to `GraphAgentDefinition` with identity default
- [ ] Ensure runtime persists the completed state before building output
- [ ] Unit tests: output round-trip, state after completion includes new turn

### A.4 `AgentInvocationRequest` extension

- [ ] Add `prior_turns: tuple[ConversationTurn, ...] = ()` to `AgentInvocationRequest` in `fred_sdk.contracts.context`
- [ ] Add `prior_turns: tuple[ConversationTurn, ...] = ()` keyword argument to `GraphNodeContext.invoke_agent` in `fred_sdk.graph.runtime`
- [ ] Add `invocation_turns: tuple[ConversationTurn, ...] = ()` to `ExecutionConfig`
- [ ] Ensure the default remains empty so all existing callers are unaffected
- [ ] Unit tests: request and execution-config serialisation with and without `prior_turns`

---

## Phase B — `TeamAgent` consumes the primitives (`fred-sdk`)

`TeamAgent` must use the general primitives from Phase A — not re-implement them.

### B.1 `TeamState` includes `ConversationalState`

- [ ] Update the shared `TeamState` class to inherit from `ConversationalState`
- [ ] Keep `TeamAgent.__pydantic_init_subclass__` assigning `state_schema = TeamState`
- [ ] Verify that `conversation_history` carries forward on turn 2 without any author override

### B.2 History append for `TeamAgent`

- [ ] Auto-generate `build_completed_state` in `TeamAgent.__pydantic_init_subclass__` to append `ConversationTurn(user_message=state.user_message, agent_response=state.final_text, agent_name=<last member name>)` after each turn
- [ ] Determine "last member name" from `state.results[-1].agent_name` when results are non-empty; use `None` otherwise

### B.3 Coordinator prompt enrichment

- [ ] Add `_format_conversation_history(history: tuple[ConversationTurn, ...]) -> str` helper in `team_api.py`
- [ ] Update `_make_member_step` to include history block in inline member prompts when `state.conversation_history` is non-empty
- [ ] Update `_make_route_coordinator_step` to include history block in the prompt when `state.conversation_history` is non-empty
- [ ] Update `_make_coordinator_step` (dynamic mode) to include history block in the prompt when `state.conversation_history` is non-empty
- [ ] Unit tests:
  - member step with history → history block present
  - route coordinator with empty history → prompt unchanged (no regression)
  - route coordinator with non-empty history → history block present in prompt
  - dynamic coordinator with history → history block present

### B.4 `_make_agent_invoke_step` passes `prior_turns`

- [ ] In `_make_agent_invoke_step`, pass `state.conversation_history` as `prior_turns` to `context.invoke_agent`
- [ ] Pass the empty tuple on first turn — no change in behaviour for first-turn invocations
- [ ] Unit tests: `invoke_agent` called with correct `prior_turns` on turn 2

---

## Phase C — Runtime enforcement (`fred-runtime`)

### C.0 Preliminary execution-seam convergence

- [x] Route `LocalRegistryAgentInvoker.invoke(...)` through `RuntimeExecuteRequest` before `_AgentExecuteRequest`
- [x] Extract runtime setup from `_iterate_runtime_event_payloads(...)` into one typed preparation path so future continuity fields land once
- [x] Keep `_AgentExecuteRequest` as the single remaining private projection boundary; do not add memory-specific plumbing on both sides
- [x] Offline validation: `make code-quality` and `make test` in `libs/fred-runtime` (2026-05-05)

### C.1 ReAct agent context injection

- [ ] In `ReActRuntime`, detect when `ExecutionConfig.invocation_turns` is non-empty
- [ ] Render `invocation_turns` with the shared formatter
- [ ] Inject the rendered context block in the system prompt: `"\n\n[Conversation context]\n{formatted_turns}"` appended after the agent's own system prompt
- [ ] Injection is transparent to the agent author — no `system_prompt_template` change is needed
- [ ] Unit tests:
  - ReAct agent invoked without `invocation_turns` → system prompt unchanged
  - ReAct agent invoked with `invocation_turns` → context block appended
  - Context block does not duplicate the current `message`

### C.2 In-process invoker forwards `prior_turns`

- [ ] Update `LocalRegistryAgentInvoker.invoke` to forward `prior_turns` into the callee execution path
- [ ] Ensure the internal execution bridge preserves `prior_turns` when calling `_iterate_runtime_event_payloads`
- [ ] Unit tests: in-process agent invocation with and without `prior_turns`

### C.3 Remote invoker forwards `prior_turns`

- [ ] Update `RemoteSseAgentInvoker.invoke` to include `prior_turns` in the HTTP payload
- [ ] Extend the runtime execute bridge so `prior_turns` reaches the callee without introducing a second public execution API
- [ ] Prefer converging the remote path on `RuntimeExecuteRequest` / typed execution plumbing rather than deepening `to_legacy_context()` usage
- [ ] Unit tests: payload construction with and without `prior_turns`

### C.4 Graph agent runtime — verify `build_completed_state` and `invocation_turns` are used

- [ ] In `GraphRuntime`, pass `ExecutionConfig.invocation_turns` into `build_turn_state`
- [ ] In `GraphRuntime._execute_loop`, call `build_completed_state` after the terminal node completes and before persisting the final checkpoint
- [ ] Unit tests:
  - after a two-turn graph agent execution, the checkpointer holds state with `conversation_history` length 2
  - invoked graph callee with no prior state receives seeded history from `invocation_turns`

---

## Phase D — Integration validation

- [ ] Write an integration scenario `fred.test.assistant` style: two-turn `route`-mode `TeamAgent` question, assert second turn routes to the correct member using history context
- [ ] Manual validation: ask the team agent "what is 4 + 4?", then ask "multiply it by 3" — assert the second question reaches the calculation sub-agent and returns 24
- [ ] Confirm all existing `fred-sdk` tests pass (A.2 default-behaviour guard)
- [ ] Confirm all existing `fred-runtime` tests pass
- [ ] `make code-quality && make test` in both `fred-sdk` and `fred-runtime`

---

## Phase E — Documentation

- [ ] Update `docs/rfc/MULTI-AGENT-MEMORY-RFC.md` status from `Draft` to `Implemented`
- [ ] Update `docs/authoring/AGENTS.md` with a multi-turn section explaining `ConversationalState`, `build_turn_state` override, and depth limits
- [ ] Add `ConversationTurn` and `ConversationalState` to `docs/platform/V2_AGENT_CREATION.md` authoring examples
- [ ] Update `docs/WORKPLAN.md` task status

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
| RFC | Draft (2026-05-05) | Consolidated design: decisions resolved, implementation plan refreshed |
| A – SDK primitives | Not started | Ready to implement |
| B – TeamAgent | Not started | Depends on A |
| C – Runtime | In progress | 2026-05-05: converged local invoker + runtime preparation path in `agent_app.py`; memory fields still pending |
| D – Integration | Not started | Depends on C |
| E – Docs | Not started | Depends on D |
