# Fred v2 Graph Runtime Contract

Audience: developers and product-minded maintainers working on v2 agents  
Status: active working contract

This document explains what the v2 graph runtime is supposed to do, and why.

The business reason is simple:

- users remember the service they were talking to
- they expect the service to remember the case, parcel, ticket, or order they already selected
- they expect the service to pause safely before important actions
- they expect the same flow to survive WebSocket, background execution, and future adapters

So the runtime contract must support more than “run a graph once”.

## 1. What A Graph Agent Is For

Use a `GraphAgentDefinition` when the business value comes from a controlled
journey, not from open-ended tool opportunism.

Typical examples:

- identify the right parcel, then explain the delay, then ask before rerouting
- qualify a support case, gather evidence, then offer a specific resolution
- triage an incident, gather system context, then ask for a human decision

In these cases, the graph is not decoration. It is the visible shape of the
service promise.

## 2. Responsibility Split

The contract is healthy only if each layer owns the right kind of responsibility.

### 2.1 What the agent definition owns

The `GraphAgentDefinition` owns the business meaning of the workflow:

- the role of the agent
- the graph structure
- the typed state shape
- the node handlers
- the final output shape
- the decision about what prior conversation state is worth carrying forward

In practice, this is where a developer says things like:

- “remember the selected parcel across turns”
- “ask the user to choose when several parcels match”
- “require a decision before rerouting”

### 2.2 What the runtime owns

The `GraphRuntime` owns the platform behavior that almost every serious graph
agent needs:

- binding runtime context
- activating tools and model access
- sequencing nodes
- emitting tool and status events
- pausing for HITL
- persisting pending checkpoints
- persisting the last completed state of the conversation
- resuming safely with explicit checkpoint identity

This is what keeps graph agents usable across transports and execution adapters.

### 2.3 What runtime services own

`RuntimeServices` own the injected external capabilities:

- model access
- tool invocation
- runtime-provided tools and MCP servers
- typed resource access for templates and supporting files
- typed artifact publication for generated outputs
- checkpointer

The graph agent should describe the business flow, not hide these dependencies
inside ad hoc client setup.

## 3. The Two Kinds Of State A Graph Runtime Must Manage

The first real postal graph exposed an important truth: a useful graph runtime
needs both kinds of state below.

### 3.1 Pending checkpoint state

This is the state of an interrupted run:

- current node
- request shown to the user
- checkpoint id
- state snapshot needed to resume

This exists so a human choice can pause the workflow and resume later without
depending on a Python object still being alive.

### 3.2 Last completed state

This is the state of the last successful completed turn for the conversation.

This exists so the next turn can feel continuous.

Examples:

- remember which parcel was selected
- remember which ticket is being discussed
- remember the last business object the user anchored on

Without this, every follow-up turn re-qualifies the same context and the agent
feels clumsy.

## 4. What Must Be Transport-Agnostic

The v2 contract must not depend on WebSocket-specific behavior.

The following must remain true whether the agent is used through:

- WebSocket streaming
- a future Temporal adapter
- a durable Postgres-backed checkpointer

Required invariants:

- pause produces a durable checkpoint identity
- resume consumes an explicit checkpoint identity when one exists
- the last completed state is keyed by conversation/thread identity
- rebuilding the runtime must not lose the meaning of a paused workflow

This is why a graph runtime cannot rely on executor-local memory for semantics.

Current Fred v2 implementation note:

- v2 runtimes now use a durable SQL-backed checkpointer over Fred's shared
  `storage.postgres` engine
- in local development this can still resolve to the SQLite fallback configured
  behind that same engine path
- this keeps the checkpoint contract stable while changing only infrastructure

## 5. Conversation History vs Runtime Checkpoints

Fred persists two different things, for two different reasons.

They are complementary, not duplicate.

### 5.1 Conversation history

Conversation history is the user-visible journal of the chat.

It answers questions such as:

- what did the user ask?
- what did the assistant answer?
- which tool calls and tool results were shown in the transcript?
- what should the UI restore after a refresh?

This is what makes a conversation look continuous to the user.

### 5.2 Runtime checkpoints

Runtime checkpoints are the machine-facing bookmark of execution.

They answer questions such as:

- was the workflow paused for HITL?
- at which exact step?
- which state must be resumed?
- which last completed state should the next turn inherit?

This is what makes execution resume correctly, rather than merely replaying the
chat transcript.

### 5.3 Why both are required

If Fred kept only conversation history:

- the UI could redraw the chat
- but an interrupted workflow could not safely resume

If Fred kept only runtime checkpoints:

- the runtime could resume
- but the user-visible conversation would not restore correctly

So the rule is:

- conversation history restores the visible dialogue
- checkpoints restore the runtime position and state

For graph agents, this distinction is especially important because the agent may
need both:

- a pending checkpoint for a paused human decision
- a last completed state so the next turn still remembers the selected parcel,
  ticket, or business object

### 5.4 The practical story in Fred v2

In a normal turn:

- the session and history stores persist the conversation
- the graph runtime may also persist the last completed state for the thread

In a HITL turn:

- the UI receives an `awaiting_human` payload
- the runtime persists a durable checkpoint with a checkpoint identity
- the conversation history still persists the visible messages around that pause

This HITL payload may represent different business shapes:

- a discrete choice among explicit options
- an approval / rejection decision
- a free-text clarification request when the workflow needs missing information

On resume:

- conversation history rebuilds what the user sees and what the model should
  remember as transcript
- the checkpoint tells the runtime where execution must continue

That is the overall persistence story of a serious v2 agent.

## 6. What The Postal Demo Taught

The postal demo revealed three runtime needs very early:

1. durable HITL checkpointing
2. carry-over state across turns
3. explicit distinction between runtime-owned persistence and agent-owned memory policy

That is not a sign that the graph approach is wrong.

It is the opposite:

- a real business workflow exposed the minimum contract a serious graph runtime
  actually needs

The important design choice is:

- the runtime stores the prior completed state
- the agent decides what from that prior state still matters for the next turn

That split is what keeps the runtime generic while allowing business continuity.

## 7. Rules Of Thumb For Future Graph Agents

When authoring a new graph agent, use these questions:

1. What business object should the user feel is still “in focus” next turn?
2. Which actions are too sensitive to execute without a human decision?
3. Which context must always be collected before proposing that action?
4. Which outputs should remain structured and visible, such as maps or links?

If those questions are central, the graph runtime should support them directly.

## 8. What Does Not Belong In The Runtime

The runtime should not decide business memory policy by itself.

For example, the runtime should not hardcode:

- “always remember the last tracking id”
- “always carry the last ticket”
- “always keep the last selected asset”

Those are business choices.

The runtime should only provide:

- a durable place to persist the completed state
- a way for the agent to rebuild the next turn state from it

## 9. Why This Matters Before Postgres Or Temporal

It is better to fix this contract now than after adding more adapters.

If the contract is right:

- adding a Postgres-backed checkpointer is an infrastructure decision
- adding a Temporal adapter is an execution adapter decision

If the contract is wrong:

- every new adapter forces a redesign of pause/resume semantics
- every new graph agent invents its own memory workaround

That is exactly what v2 is meant to avoid.

## 10. Bottom Line

The v2 graph runtime is not just “a way to execute graph nodes”.

It is the platform layer that makes workflow-shaped agents feel like real
services:

- continuous across turns
- safe around user decisions
- durable across execution adapters
- explicit enough for business demos and production reasoning

That is the standard future graph agents should be written against.
