# Multi-Agent Conversational Memory

**Status**: As-built design for MEMORY-01 phases A-E, implemented 2026-05-05

This document describes the implemented cross-turn memory contract for graph
agents and agent-to-agent calls. It replaces the implemented RFC as the stable
design reference.

## Purpose

Graph agents, including `TeamAgent`, need enough conversation continuity to
answer follow-up turns such as "multiply it again" without requiring each agent
author to rebuild memory plumbing. The feature is intentionally a general SDK
primitive, not a TeamAgent-specific patch.

The design has three boundaries:

- SDK state contracts decide what history exists and how it is carried.
- Runtime execution injects received history into graph or ReAct executions.
- Agent invocation transports forward only typed conversation turns, not raw
  caller state.

## Core SDK Types

`ConversationTurn` lives in `fred_sdk.contracts.context` and is the portable
turn unit:

- `user_message`
- `agent_response`
- optional `agent_name`

`ConversationalState` is a state mixin with:

- `conversation_history: tuple[ConversationTurn, ...] = ()`

Agent definitions opt in by using a state model that includes
`ConversationalState`. Agents that do not opt in keep their previous behavior.

## Turn State Carry-Forward

`GraphAgentDefinition.build_turn_state(...)` is the standard turn-entry hook.
It receives the current input, binding, optional previous completed state, and
optional `invocation_turns`.

The default carry policy is explicit:

- `GraphAgentDefinition._turn_carry_fields()` returns the fields that may cross
  turn boundaries.
- The default implementation carries only `conversation_history` when the
  previous state has it.
- When there is no previous state, `invocation_turns` may seed
  `conversation_history` for invoked graph agents.
- `conversation_history_max_turns` defaults to `20` and is applied during
  carry-forward and invocation seeding.

This makes the persisted graph state the source of truth while avoiding broad
state copying between turns.

## Completion Hook

`GraphAgentDefinition.build_completed_state(state)` runs after the terminal
node and before the final checkpoint is persisted. The default implementation is
identity.

Agents that need to append a new turn override this hook. `TeamAgent` generates
an implementation automatically and appends:

- the original user message
- the final text
- the last member agent name, when available

Current limitation: the generated `TeamAgent` append does not yet apply
`conversation_history_max_turns`. This is tracked as MEMORY-05 in the hardening
RFC.

## TeamAgent Behavior

`TeamState` includes `ConversationalState`, so TeamAgent participates in the
generic graph memory contract.

TeamAgent consumes history in three places:

- coordinator prompts include a rendered prior-history block when history is
  present;
- inline member prompts include the same history block;
- agent-invoke member steps pass `state.conversation_history` as `prior_turns`.

This lets the team leader and invoked members see the relevant prior exchange
without sharing the whole caller graph state.

## Agent Invocation Boundary

`AgentInvocationRequest` carries:

- `message`
- portable runtime context
- optional invocation scope
- `prior_turns: tuple[ConversationTurn, ...] = ()`

`GraphNodeContext.invoke_agent(..., prior_turns=...)` exposes that field to
graph nodes. Runtime execution maps `prior_turns` into
`ExecutionConfig.invocation_turns` for the callee.

The invocation boundary deliberately does not merge callee history back into the
caller. The caller owns its conversation history; the callee receives prior
turns as context for the current call.

## Runtime Behavior

Graph runtimes pass `ExecutionConfig.invocation_turns` into
`GraphAgentDefinition.build_turn_state(...)`. If the callee has no previous
state, those turns can seed the callee's `conversation_history`.

ReAct runtimes render `invocation_turns` as a leading system message before the
input transcript. This avoids changing cached ReAct system prompts while still
making prior turns visible to the model.

Local and remote invokers both forward prior turns today. Their request-shape
convergence is not complete:

- the local invoker still hand-builds the private `_AgentExecuteRequest`;
- the remote SSE invoker still sends a legacy `message` / `context` payload.

Those two gaps are tracked as MEMORY-03 and MEMORY-04 in the hardening RFC.

## Checkpoint Semantics

Conversational memory is persisted in runtime checkpoints, not in a separate
long-term memory store.

As built, graph checkpoint keys are derived from the public `session_id` and
GraphRuntime writes LangGraph checkpoints with an empty `checkpoint_ns`. ReAct
execution maps `ExecutionConfig.session_id` to LangGraph `thread_id` without an
agent-specific namespace.

This preserves session continuity, but it does not yet isolate checkpoint state
per agent inside the same session. Agent-scoped checkpoint isolation is tracked
as MEMORY-02 in the hardening RFC.

## Non-Goals

The current design does not provide:

- long-term semantic memory;
- memory summarization;
- cross-session memory;
- arbitrary caller/callee state sharing;
- automatic merging of callee state back into caller state;
- a second graph engine or a replacement checkpoint store.

## Operational Guidance

When touching this area:

- keep `ConversationTurn` as the cross-agent memory currency;
- preserve `session_id` as the public conversation identity;
- use explicit state carry-forward instead of copying whole state models;
- keep local, remote, graph, and ReAct execution paths on the same public
  `RuntimeExecuteRequest` direction where possible;
- add regression tests before changing checkpoint key or namespace behavior,
  because HITL resume depends on stable LangGraph checkpoint lookup.
