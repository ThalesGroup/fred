# RFC: Multi-Turn Conversational Memory for Graph Agents

- Status: Draft
- Authors: Fred core team
- Intended audience: Fred maintainers, SDK contributors, agent authors
- Scope: Cross-turn memory contract for graph agents, `invoke_agent` context propagation, `TeamAgent` multi-turn behaviour
- Non-goals: Long-term cross-session memory, vector-store semantic recall, user preference persistence

---

## 1. Summary

Fred graph agents — including `TeamAgent` — are currently **stateless across turns by design**. Each turn starts from a blank state derived only from the current user message. This is correct for single-shot workflows but is a fundamental design flaw for conversational use cases where the user expects the agent to remember what was discussed one turn ago.

This RFC defines a **general, composable mechanism for cross-turn conversational memory** in graph agents. The solution must not be a `TeamAgent`-specific patch. It must be a first-class contract that any graph agent — team or otherwise — can opt into, and that the framework enforces consistently across all layers: state, routing, and agent invocation.

Architectural intent:

- LangGraph continues to own node scheduling, checkpoint persistence, resume, and graph execution semantics.
- Fred continues to own the declarative authoring facade and the typed continuity contract around it.
- If a future proposal requires a second graph engine, custom reducers, custom edge semantics, or a parallel checkpoint stack, that proposal is outside the scope of this RFC.

---

## 2. Problem Statement

### 2.1 Three independent failure points

The memory gap manifests at three distinct layers. Each can be reproduced independently and each requires an independent fix. A patch at any single layer leaves the other two broken.

**Layer 1 — The graph state does not carry prior turns**

`GraphAgentDefinition.build_turn_state()` receives `previous_state` from the checkpointer but the default implementation ignores it. Every graph agent, including `TeamAgent`, starts each turn with a blank state. The user's prior messages, prior answers, and the context of the ongoing conversation are all discarded.

`TeamState` in particular carries only `user_message`, `results`, and `final_text`. These three fields are all within-turn; none of them crosses the turn boundary.

**Layer 2 — The coordinator cannot route on prior context**

In `route` and `dynamic` modes, the coordinator LLM sees only `state.user_message` — the current turn's text. It has no knowledge that a prior turn existed, what was asked, or what was answered. A follow-up question such as "can you go deeper on the second point?" gives no routing signal to a context-blind coordinator. It will guess or fall back to the first member.

The `_make_route_coordinator_step` and `_make_coordinator_step` helpers both build their prompts from `state.user_message` only.

**Layer 3 — Sub-agents invoked via `invoke_agent` receive no conversation context**

`context.invoke_agent(agent_id, message)` passes `state.user_message` — the current turn's text only. The target sub-agent starts a fresh execution against the team's `session_id`. It has no knowledge of what the user discussed in prior turns. If the sub-agent is a ReAct agent, it will search its own history for that `session_id`, but it may have been called for the first time in this turn, making its history empty.

`AgentInvocationRequest` currently carries no mechanism to forward context from the calling graph agent to the target agent.

### 2.2 The unifying root cause

These three failures share one root cause: **the `TeamState` model (and graph agent state in general) has no general concept of conversation history**. It has no slot for prior turns, so prior turns cannot be:

- read by `build_turn_state` when starting a new turn,
- included in coordinator prompts,
- forwarded to sub-agents via `invoke_agent`.

### 2.3 What the correct behaviour should be

When a user sends a second message to a team agent:

1. The coordinator must know that a prior turn happened, what was asked, and what the team's last answer was. It uses this context to route correctly.
2. The selected sub-agent must receive enough context to understand the follow-up without requiring the user to repeat themselves.
3. After the turn, the new exchange is appended to the history so that turn 3 sees turns 1 and 2.

---

## 3. Design Principles

These principles take precedence over all implementation decisions. A proposed change that violates any of them must be revised.

**P1 — No use-case-specific code.**
Memory is not a `TeamAgent` feature. It is a general capability of the graph agent contract. The fix must live in the shared SDK primitives (`ConversationTurn`, `build_turn_state`, `AgentInvocationRequest`) and flow naturally to `TeamAgent` as a consumer, not as a special case.

**P2 — Opt-in, not opt-out.**
Existing graph agents that do not declare a history field must not be affected. The mechanism is available to authors who include it in their state schema. `TeamAgent` opts in automatically via its `__pydantic_init_subclass__` hook, but single-turn workflow agents are unaffected.

**P3 — The state is the source of truth for memory.**
Conversation history lives in the graph state and is persisted by the checkpointer. It is not stored separately, it is not fetched from the history store at routing time, and it is not reconstructed from SSE logs. The checkpointer already persists state between turns — using it correctly is sufficient for short-session memory.

**P4 — The `invoke_agent` boundary must be respected.**
Sub-agents are independent. They do not inherit the team leader's internal state. Cross-agent context propagation happens through the `AgentInvocationRequest` contract, not through shared state or runtime singletons. The receiving agent decides how to use the provided context.

**P5 — Composable primitives over opinionated abstractions.**
The shared type (`ConversationTurn`) and the state mixin (`ConversationalState`) must be useful independently of `TeamAgent`. An author building a custom graph agent — not using `TeamAgent` at all — should be able to use these primitives to get the same multi-turn behaviour.

---

## 4. Proposed Design

### 4.1 `ConversationTurn` — shared exchange record

A new model added to `fred-sdk` (`fred_sdk.contracts.models`) representing one completed user–agent exchange:

```python
class ConversationTurn(FrozenModel):
    user_message: str
    agent_response: str
    agent_name: str | None = None   # set when a named sub-agent produced the response
```

This model is deliberately narrow. It is the minimum needed to let a coordinator or sub-agent understand what happened. It is not a full message trace. It does not embed tool calls, sources, or streaming events — those live in the history store (for UI replay) and in LangGraph checkpoints (for within-turn recovery).

`agent_name` is optional so the type works for both plain graph agents (no named member) and team agents (coordinator names the member that answered).

### 4.2 `ConversationalState` — opt-in history mixin

A new Pydantic model added to `fred-sdk` that any graph state class can include via composition:

```python
class ConversationalState(BaseModel):
    conversation_history: tuple[ConversationTurn, ...] = ()
```

Authors compose this into their state:

```python
class MyAgentState(ConversationalState, BaseModel):
    user_message: str
    result: str = ""
```

`TeamAgent` should use the same primitive directly: the shared `TeamState` inherits
from `ConversationalState`, and `TeamAgent.__pydantic_init_subclass__` continues
to assign `state_schema = TeamState`. No generated per-subclass state mixin is
required.

### 4.3 `GraphAgentDefinition.build_turn_state` — explicit carry-forward contract

The hook signature already exists. The contract is extended with a clear specification:

> The base implementation carries forward only fields explicitly declared by the
> agent as cross-turn continuity fields. It does **not** carry all overlapping
> fields from `previous_state`.

The default implementation changes from:

```python
def build_turn_state(self, input_model, binding, previous_state=None):
    return self.build_initial_state(input_model, binding)
```

to:

```python
conversation_history_max_turns: ClassVar[int] = 20

def _turn_carry_fields(self) -> frozenset[str]:
    state_fields = self.state_model().model_fields
    return (
        frozenset({"conversation_history"})
        if "conversation_history" in state_fields
        else frozenset()
    )

def build_turn_state(
    self,
    input_model,
    binding,
    previous_state=None,
    invocation_turns: tuple[ConversationTurn, ...] = (),
):
    base = self.build_initial_state(input_model, binding)
    carry_fields = self._turn_carry_fields()
    if not carry_fields:
        return base

    if previous_state is not None:
        shared = (
            carry_fields
            & set(base.model_fields)
            & set(previous_state.model_fields)
        )
        updates: dict[str, object] = {}
        for field_name in shared:
            value = getattr(previous_state, field_name)
            if field_name == "conversation_history":
                value = tuple(value[-self.conversation_history_max_turns :])
            updates[field_name] = value
        return base.model_copy(update=updates) if updates else base

    if invocation_turns and "conversation_history" in carry_fields:
        return base.model_copy(
            update={
                "conversation_history": tuple(
                    invocation_turns[-self.conversation_history_max_turns :]
                )
            }
        )

    return base
```

This is intentionally narrow:

- `user_message`, `final_text`, and other within-turn scratch fields always come
  from the current turn unless an author explicitly opts them into carry-forward.
- A state model that includes `ConversationalState` gets `conversation_history`
  carry-forward automatically with no custom override.
- When a graph agent is invoked by another agent, `invocation_turns` seeds the
  initial `conversation_history` only when there is no prior completed state for
  that callee session. Existing callee state wins over caller-provided context.

### 4.4 History append — `build_completed_state` closes the loop

The runtime currently persists completed graph state before calling
`build_output`. Therefore memory append cannot live in `build_output` without
changing that contract. The general hook is:

```python
def build_completed_state(self, state: BaseModel) -> BaseModel:
    return state
```

Runtime rule:

1. terminal node finishes with `state`
2. runtime computes `completed_state = build_completed_state(state)`
3. runtime persists `completed_state` to the checkpointer as the latest completed state
4. runtime calls `build_output(completed_state)`

`TeamAgent` auto-generates `build_completed_state` to append a
`ConversationTurn(user_message=..., agent_response=state.final_text, agent_name=<last member name>)`.

### 4.5 Prompt enrichment — consequence of the state fix

Once `conversation_history` is in state and carried forward, prompt-building
helpers become history-aware by using one shared renderer:

```python
def _format_conversation_history(
    history: tuple[ConversationTurn, ...],
) -> str:
    ...
```

This helper is used in three places:

- `_make_route_coordinator_step` includes prior turns when routing the next user question
- `_make_coordinator_step` includes prior turns in dynamic mode
- `_make_member_step` includes prior turns in inline member prompts, in addition
  to same-turn `results`

This is not a separate feature. It is the natural consequence of having history in state.

### 4.6 `AgentInvocationRequest` — typed prior turns for sub-agents

```python
class AgentInvocationRequest(FrozenModel):
    agent_id: str
    message: str
    context: PortableContext
    prior_turns: tuple[ConversationTurn, ...] = ()
```

This stays typed end-to-end. That is intentional:

- the invoke boundary is part of Fred's own contract, not an external third-party API
- `ConversationTurn` is already the SDK's canonical short-term memory model
- a typed tuple is safer than an opaque formatted string and keeps formatting decisions in one shared place

`GraphNodeContext.invoke_agent` signature gains an optional keyword argument:

```python
async def invoke_agent(
    self,
    agent_id: str,
    message: str,
    *,
    prior_turns: tuple[ConversationTurn, ...] = (),
) -> AgentInvocationResult:
```

`_make_agent_invoke_step` in `route` mode passes
`state.conversation_history` as `prior_turns`.

Both transport paths must forward the field unchanged:

- `LocalRegistryAgentInvoker`
- `RemoteSseAgentInvoker`

The remote path must reuse the existing runtime execute transport. Do not add a
second public execution API just for agent-to-agent calls; keep any bridge logic
internal to the runtime.

### 4.7 Callee runtime behaviour

`ExecutionConfig` gains a typed field:

```python
invocation_turns: tuple[ConversationTurn, ...] = ()
```

This lets both runtime categories receive the same structured caller context.

#### ReAct callee

When a ReAct agent receives non-empty `invocation_turns`, the runtime renders
them with the shared formatter and prepends the result as a structured block in
the system prompt:

```
[Conversation context from calling agent]
{formatted_prior_turns}
```

This is injected at the `ReActRuntime` layer, not in the ReAct agent's
authoring code. Authors writing ReAct agents need not know they may be called
from a team.

#### Graph callee

`GraphRuntime` passes `ExecutionConfig.invocation_turns` to
`build_turn_state(...)` as `invocation_turns`. A graph callee whose state
includes `ConversationalState` therefore receives the same short-term memory on
its first invoked turn without any TeamAgent-specific code.

### 4.8 History depth limit

Unbounded history accumulation raises two risks: context window overflow, and checkpointer storage growth. The general contract specifies:

- Default maximum: last **20 turns** via
  `GraphAgentDefinition.conversation_history_max_turns = 20`.
- Configurable per agent by overriding that class variable on the definition.
- Truncation is oldest-first (sliding window, not summarisation — summarisation is deferred).

This limit is enforced in `build_turn_state` both when carrying forward prior
state and when seeding a callee from `invocation_turns`, not in storage.

---

## 5. What This RFC Does Not Cover

The following are explicitly deferred. They may become separate RFCs.

**A second graph engine:** This RFC does not introduce custom graph scheduling,
custom edge semantics, custom reducers, or a parallel persistence model. LangGraph
remains the executor.

**Cross-session memory (long-term memory):** Remembering what a user said last week requires a semantic retrieval mechanism (vector store, structured DB, or explicit memory tool). This RFC only addresses within-session short-term memory via the checkpointer.

**Memory summarisation:** When a conversation exceeds the depth limit, the correct behaviour is to summarise old turns rather than truncate them. This requires an LLM summarisation step and a new graph node. Deferred.

**Sub-agent state sharing:** A sub-agent invoked via `invoke_agent` does not
share checkpointer state with the calling team. Full state sharing requires a
Temporal child-workflow model or a shared checkpointer namespace. Both are out
of scope. `prior_turns` is the bounded, safe alternative.

**Merging callee history with caller-provided history when both exist:** The
initial rule is simple: a callee's own `previous_state` wins, and
`invocation_turns` only seeds first use. More advanced merge/dedup semantics are
deferred until a real use case appears.

---

## 6. Contract Changes Summary

| Component | Change | Layer |
|---|---|---|
| `fred_sdk.contracts.models.ConversationTurn` | New model | fred-sdk |
| `fred_sdk.contracts.models.ConversationalState` | New mixin | fred-sdk |
| `fred_sdk.contracts.models.GraphAgentDefinition.build_turn_state` | Default explicit carry-forward + `invocation_turns` seeding | fred-sdk |
| `fred_sdk.contracts.models.GraphAgentDefinition._turn_carry_fields` | New hook for per-agent continuity fields | fred-sdk |
| `fred_sdk.contracts.models.GraphAgentDefinition.build_completed_state` | New hook for terminal-state normalization before persistence | fred-sdk |
| `fred_sdk.contracts.models.GraphAgentDefinition.conversation_history_max_turns` | New per-agent depth limit class variable | fred-sdk |
| `fred_sdk.contracts.context.AgentInvocationRequest` | Add `prior_turns: tuple[ConversationTurn, ...]` | fred-sdk |
| `fred_sdk.contracts.runtime.ExecutionConfig` | Add `invocation_turns: tuple[ConversationTurn, ...]` | fred-sdk |
| `fred_sdk.graph.runtime.GraphNodeContext.invoke_agent` | Add `prior_turns` kwarg | fred-sdk |
| `fred_sdk.graph.authoring.team_api.TeamState` | Include `ConversationalState` | fred-sdk |
| `fred_sdk.graph.authoring.team_api.TeamAgent` | Auto-generate history append via `build_completed_state` | fred-sdk |
| `fred_sdk.graph.authoring.team_api._make_member_step` | Include history in inline member prompts | fred-sdk |
| `fred_sdk.graph.authoring.team_api._make_route_coordinator_step` | Include history in prompt | fred-sdk |
| `fred_sdk.graph.authoring.team_api._make_coordinator_step` | Include history in prompt | fred-sdk |
| `fred_sdk.graph.authoring.team_api._make_agent_invoke_step` | Pass `prior_turns` to `invoke_agent` | fred-sdk |
| `fred_runtime.graph.graph_runtime.GraphRuntime` | Pass `invocation_turns` to `build_turn_state`; persist `build_completed_state(state)` | fred-runtime |
| `fred_runtime.react.react_runtime.ReActRuntime` | Inject formatted `prior_turns` into system prompt when present | fred-runtime |
| `fred_runtime.app.agent_app.LocalRegistryAgentInvoker` | Forward `prior_turns` into in-process execution | fred-runtime |
| `fred_sdk.runtime_support.remote_agent_invoker.RemoteSseAgentInvoker` | Forward `prior_turns` over existing execute transport | fred-sdk |

All changes are additive or default-behaviour changes. No existing graph agent or test breaks.

---

## 7. Resolved Design Decisions

**D1 — Carry-forward uses explicit carry fields, not reset fields.**
The SDK must not carry arbitrary overlapping fields from `previous_state`, or
the current turn input can be silently overwritten. The contract therefore uses
`_turn_carry_fields()` with a conservative default.

**D2 — Agent-to-agent context propagation stays typed.**
`AgentInvocationRequest` carries `prior_turns: tuple[ConversationTurn, ...]`,
not a pre-rendered string. Prompt formatting happens in one shared renderer at
the callee runtime boundary.

**D3 — The history limit is an agent definition choice, not a pod setting.**
`conversation_history_max_turns` lives on `GraphAgentDefinition` with a default
of `20`. If operators later need a pod-level cap, that should be introduced as
an explicit upper bound rather than replacing the authoring-level setting.

**D4 — History append happens in `build_completed_state`, not `build_output`.**
`build_output` remains output-only. The runtime persists `build_completed_state(state)`
and then derives the final output from that completed state.

**D5 — Invoked graph agents are first-class, not second-class.**
The transport contract and runtime wiring must support both ReAct and graph
callees. This RFC does not stop at ReAct system-prompt injection.

---

## 8. Acceptance Criteria

- Any graph agent whose state includes `ConversationalState` automatically carries `conversation_history` across turns without overriding `build_turn_state`.
- Any graph agent invoked via `invoke_agent` receives caller `prior_turns` as typed `invocation_turns` on its first invoked turn when no prior callee state exists.
- A `TeamAgent` in `route` mode answers a follow-up question correctly whether the selected specialist is a ReAct agent or a graph agent.
- A sub-agent invoked via `invoke_agent` receives the prior conversation as typed turns; ReAct callees see it in the prompt, and graph callees see it through `build_turn_state(..., invocation_turns=...)`.
- A graph agent whose state does not include `ConversationalState` is completely unaffected — its behaviour, tests, and state schema are unchanged.
- All existing `fred-sdk` and `fred-runtime` tests pass without modification.
- New unit tests cover: carry-forward with and without history, invocation seeding, coordinator/member prompts with history, `invoke_agent` with and without `prior_turns`, `build_completed_state`, ReAct prompt injection, and graph callee seeding.
