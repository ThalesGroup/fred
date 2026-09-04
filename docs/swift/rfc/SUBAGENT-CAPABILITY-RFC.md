# RFC — Sub-agent Capability: an agent delegates work to fresh-context copies of itself

**Status:** Tier 1 slice 1 (#2525), §5.6 HITL (#2526) and the result surface (#2529) shipped 2026-09-03; §5.2 prompt mode and §7 token accounting still open (#2527-#2528). Tiers 2-3 not specified.
**Author:** Florian Muller
**Date:** 2026-09-03
**Area:** `fred-sdk` (contracts), `fred-runtime` (invoker, capability block), new capability package
**Tracking:** [#2520](https://github.com/ThalesGroup/fred/issues/2520) (parent); tier 1 sub-issues #2525 → #2526, #2527, #2528, #2529 (see §13)
**Related:** `RUNTIME-EXECUTION-CONTRACT.md` §14 (frozen `invoke_agent` surface),
`MULTI-AGENT-MEMORY-HARDENING-RFC.md` (MEMORY-02, MEMORY-06),
`design/MULTI_AGENT_MEMORY.md`, `capabilities/AUTHORING.md`,
the `add-fred-capability` skill.

---

## 1. Problem

A ReAct agent has no way to delegate. Faced with a task that decomposes into
several independent pieces — read five documents and compare them, draft three
variants, investigate four hypotheses — it must do all of it in one linear
message history. Every intermediate result stays in context, the transcript
grows past the point where the model attends to it well, and the pieces run
one after another even when nothing couples them.

An agent-to-agent primitive already exists and is live: `AgentInvokerPort` /
`LocalRegistryAgentInvoker` / `GraphNodeContext.invoke_agent`
(`RUNTIME-EXECUTION-CONTRACT.md` §14). It is reachable only from **Graph**
nodes. Its only production consumer is the external `fred-rags` pod; no ReAct
agent can call it, and no capability tool uses it, even though
`RuntimeServices.agent_invoker` is populated on every request.

This RFC adds the missing ReAct-side surface as a capability: one tool that
runs a fresh-context copy of the calling agent against a prompt the parent
writes.

## 2. Reuse audit (2026-09-03)

Checked before proposing anything new:

| Existing thing | Verdict |
| -------------- | ------- |
| `AgentInvokerPort` / `LocalRegistryAgentInvoker` (`agent_app.py:597`) | **Reused.** This RFC extends it; it does not add a second invocation path. |
| `GraphNodeContext.invoke_agent` (`graph_runtime.py:815`) | Untouched. Graph agents keep calling it directly. |
| `TeamAgent` (`fred_sdk/graph/authoring/team_api.py:728`) | Not the answer here — Graph-only, coordinator-driven, and registered by no pod in this repo. See §9. |
| LangChain / `deepagents` sub-agent features | Rejected. A recorded position (2026-08-12 operation-concept validation) keeps model and operation routing Fred-owned; a naked `create_agent` in a tool would bypass identity delegation, model routing, KPI and tracing. |
| Issue #1859 (`InvocationScope` can widen) | Out of scope — this capability never sets `scope`. See §10. |

## 3. Goals

1. One tool, `run_subagent`, that runs a copy of the calling agent with a fresh
   context and a parent-authored prompt, and returns its answer.
2. Same agent, same tools: the child inherits the parent's `agent_id` and its
   full capability selection with the same config.
3. Bounded recursion, enforced where the tool is built, not deep in the runtime.
4. Sub-agent token spend is measurable per child.
5. No new execution stack: the child is an ordinary Fred agent turn.

## 4. Non-goals (POC)

- **No async.** The parent blocks until its children return. (Parallelism is
  still real — see §6.4.)
- **No follow-up messaging.** A parent cannot talk to a running or finished
  child. This is the main driver for a later checkpoint-bearing design (§11.1).
- **No `model` parameter.** Design recorded in §11.2, deliberately deferred.
- **No timeout, no SSE keepalive.** Known limitations, §10.
- **No sub-agent UI.** One tool-call line in the chat, like any other tool.
- **MEMORY-02 and MEMORY-06 are not closed.** This RFC bounds recursion on its
  own path only; Graph and `TeamAgent` callers stay as they are.

## 5. What a sub-agent is

### 5.1 Identity

The child runs the **same `agent_id`** as the parent and inherits the parent's
already-resolved `AgentTuning` — the capability selection and each capability's
config. It is the same agent, with the same tools and the same hooks.

The parent's resolved tuning is reused rather than re-resolving
`agent_instance_id` through control-plane: the parent resolved that exact
instance moments earlier in the same request. (A child turn still performs one
ReBAC lookup for usable model ids inside `_iterate_runtime_event_payloads`;
that is the runtime's own invariant and is not touched here.)

**What "same tools" actually requires (code check, 2026-09-03).** Today the
invoker calls `_iterate_runtime_event_payloads` with `agent_instance_id=None`
and **none** of `tuning`, `capability_registry`, `team_settings`,
`exchange_id` or `reasoning_enabled_model_ids` (`agent_app.py:657-677`).
A child run through the invoker therefore has **no capabilities and no
tools at all** — `_build_capability_block` receives `tuning=None`. "Tuning
propagation" in §8 means carrying all of the following privately on
`LocalRegistryAgentInvoker`, exactly as `platform_chat_model_binding` is
carried today (never on the request, which a caller can forge):

| Carried privately | Why the child needs it |
| ----------------- | ---------------------- |
| `tuning` (`AgentTuning`) | capability selection + per-capability config |
| `capability_registry` | without it the block is never built |
| `team_settings` | per-team capability enablement |
| `agent_instance_id` | `CapabilityIdentity`; capabilities that key storage on the instance (agent-config filesystem area) must see the parent's instance, not `None` |
| `exchange_id` | KPI/trace correlation with the parent turn |
| `reasoning_enabled_model_ids` | same reasoning policy as the parent |
| `turn_options` | the invoker path has no other channel for them (§5.4) |
| the parent's `BoundRuntimeContext` | the only place the per-turn retrieval selections live (§5.4) |

As built: `RUNTIME-EXECUTION-CONTRACT.md` §8.63.

Graph callers of `invoke_agent` keep today's behaviour for cross-agent calls:
these values are only forwarded when the child `agent_id` equals the parent's.
A different agent must still be resolved on its own terms.

### 5.2 Prompt

`compose_system_prompt` (`react_prompting.py:308`) builds eight layers. The
child gets:

| Layer | Child |
| ----- | ----- |
| 1. rendered agent template | **replaced** — a short sub-agent framing + the parent's `prompt` argument |
| 2. runtime tool descriptions | kept |
| 3. definition guardrails | kept |
| 4. global base output contract | kept |
| 5. tool-failure recovery notice | kept |
| 6. runtime-specific suffixes | kept |
| 7. user-selected context prompts | **dropped** |
| 8. conversation attachments | **dropped** |

Layers 2–6 are runtime-owned invariants; dropping them would break tool use and
output formatting for the tools the child is meant to keep. Layers 7–8 are the
user's conversation context, which the child has no user for.

The framing itself is short and states: this is a sub-agent run, there is no
user, do not ask questions, return the answer as text, and that tools requiring
human approval are unavailable or will refuse (§5.6).

**Two ways to handle layer 1 — both are to be evaluated in the POC**
(decision 2026-09-03, developer review). The table above shows mode R.

Mode A is live; mode R needs the `system_prompt` override of §6.7, and #2527
closes this section's remaining question.

- **Mode R — replace.** Layer 1 becomes framing + the parent's `prompt`. A
  parent template written for a human ("the user will ask you…") cannot mislead
  a child that has no user. Cost: **a child inherits no persona, tone, output
  language or business rule from its parent's template.** A template that says
  "always answer in French" produces children that do not, unless the parent
  restates it in every call — a tax the model will forget. Mode R uses the
  system-prompt override on `AgentInvocationRequest` (§6.7).
- **Mode A — append.** Framing first, then the parent's template kept verbatim
  as *inherited instructions*, with the framing stating that there is no user
  and that any "ask the user" instruction in the template does not apply. The
  parent's `prompt` travels as the child's `message` (the user turn), so no
  invocation contract changes. Cost: template text that argues with the framing
  ("greet the user", "end with a question") may confuse the child.

Evaluation criteria: output language and persona retention across ≥3 agents
whose templates carry such rules; frequency of the child asking questions or
addressing a user; prompt-token overhead per child. Whichever wins, the layer
table above is updated and the other mode deleted from this RFC.

### 5.3 State

The child runs **without a checkpointer**. `RuntimeServices` is built fresh per
request, so this is a per-run substitution, not a change to anyone else's
checkpoint behaviour.

Rationale: a sub-agent is one turn and is never resumed. Fresh context then
holds by construction, with no dependence on session identity. The alternative
— reusing the parent's `session_id`, which ReAct maps straight to LangGraph's
`thread_id` (`react_message_codec.py:230`) — would make the child **load the
parent's checkpoint**, seeing the whole conversation and able to overwrite the
parent's state mid-turn. That is the tracked MEMORY-02 gap; this design
sidesteps it rather than pretending to fix it.

Two consequences, both accepted:

- **No resume, therefore no interrupt**: gated tools are hidden or refused (§5.6).
- Revisiting this is the first thing follow-up messaging requires (§11.1).

The child keeps the parent's `session_id` in its portable context, so KPI
grouping by conversation stays correct. No history row is written for a child:
`_write_turn_history` is called only from `_stream` (`agent_app.py:2811`), which
the invoker bypasses — so children cannot appear as phantom conversations in the
session list, whatever session id they carry.

### 5.4 Inherited context

**Corrected 2026-09-03 (#2525, code check).** An earlier draft said the
invoker's existing `PortableContext` copy already carried the caller's
`RuntimeContext` selections down. It does not: `PortableContext` is
`extra="forbid"` and has no `selected_document_uids`,
`selected_document_libraries_ids` or `search_policy` field at all, so every
child ever invoked answered over the full corpus. As built, a same-agent
child's context is derived from the parent's own `RuntimeContext` (carried on
the private `_ParentTurn`, §5.1), minus the user's conversation context
(`context_prompt_text`, `attachments_markdown` — layers 7–8 of §5.2), the
resume fields, and the access token. Cross-agent children still get only the
caller-supplied `PortableContext`, unchanged.

`turn_options` are **also inherited**, for consistency with that. The only
turn options that exist are `DocumentAccessTurnOptions`
(`document_access/capability.py:318`): `library_tag_ids` and `document_uids`,
from the `document_scope` composer widget. If they did not flow down, a user who
narrowed their agent to one folder would get children searching the full corpus
— the same widening failure #1859 describes, arriving through a different door.

> **Invariant this rests on:** turn options *narrow, never widen* — stated in
> `DocumentAccessTurnOptions`' own docstring ("intersected with the capability
> config scope (never widening it)"). A future turn option that grants rather
> than restricts would make blind inheritance wrong, and must revisit this
> section.

### 5.5 Depth

`CapabilityContext` gains `invocation_depth: int = 0`, threaded from
`_iterate_runtime_event_payloads` through `_build_capability_block` into every
capability's context. Additive with a default, so no existing capability
changes. It is deliberately its own field rather than part of
`CapabilityIdentity`, which answers "who", not "how deep".

The counter is carried as a **private attribute on the invoker**, following the
`platform_chat_model_binding` precedent (`agent_app.py:617-628`): never on
`RuntimeContext`, `PortableContext` or `AgentInvocationRequest`, so a crafted
request cannot pin `depth: 0` and recurse without limit. `LocalRegistryAgentInvoker`
at depth *d* re-enters the turn path at *d+1*.

Nothing is persisted. Depth is a property of one execution, not of an agent: the
same instance runs at depth 0 for a user and depth 1 for a parent, concurrently,
in the same pod.

Enforcement is **capability-side**, in `tools()`: at `max_depth` the tool is
simply not returned, so a leaf child never sees it. `max_depth` is a clamped
config field (default 3, ceiling 5), following the `platform_postgres`
`statement_timeout_s` idiom. There is deliberately **no second limit** in the
invoker — one bound, one place.

Depth bounds height, not size. Fan-out is bounded by the agent's existing
`ToolSelectionPolicy.max_tool_calls_per_turn` (`react_tool_loop.py:98`), since
each launch is a tool call. That knob is `None` on most agents today, so
**fan-out is unbounded by default**. **Decided 2026-09-03: accepted, no
dedicated cap.** A user can already spend without limit by sending turns;
accountability belongs to a usage/quota surface (§11.2). The one difference
the performance review must weigh is that turns are sequential per
conversation while fan-out is concurrent in one pod (§6.4).

> **Reopened and re-decided 2026-09-03 (#2525 performance review), tracked in
> [#2531](https://github.com/ThalesGroup/fred/issues/2531).** The premise above
> is wrong twice: `max_tool_calls_per_turn` is set (12 on five agents, 30 on
> `platform_ops`), and it maps to a **per-graph-run** limit, so a child — its
> own graph run — resets the counter and it bounds nothing across depth. Real
> worst case at `max_depth=3` is ~1 900 concurrent agent turns for one user
> message, against a 500-connection pool per pod. §6.5's per-child content cap
> has the same shape. **Decision: unbounded for the POC, to be settled with POC
> data on #2531.**

### 5.6 HITL — shipped

Decided 2026-09-03 (option B: `FredHitlMiddleware`, depth threaded to the
frame) and implemented. The durable what/why is
`../design/RUNTIME-EXECUTION-CONTRACT.md` §8.64: unconditionally gated tools
hidden from a child's model, anything else that would gate refused with an
error tool result, depth 0 unchanged. Nothing open here.

## 6. The tool

### 6.1 Shape

`run_subagent`, from a standalone package `libs/fred-capability-subagent`
(capability id `subagent`), depending only on `fred-sdk` —
`AgentInvokerPort` and `RuntimeServices` are both SDK types. One entry-point
line, per `AUTHORING.md`.

Arguments:

| Argument | Presence |
| -------- | -------- |
| `prompt: str` | always, required |
| `kind: enum` | only when more than one kind is available |
| `model` | not in V1 (§11.2) |

### 6.2 Schema principle — an argument appears only when there is a real choice

`kind` is implemented but, with `"self"` as the only value, is **absent from the
schema**. When a later version lets an admin configure named kinds, it appears
by itself. The same rule governs `model` when it lands: one usable model, no
argument.

An enum with one legal value costs schema tokens on every turn and gives the
model a decision it cannot get right or wrong.

### 6.3 Dynamic description, and the cache rule

`tools()` runs once per turn (`assembly.py:367`), so the tool description is
built per turn and carries the remaining depth and the parallelism instruction
(§6.4) — never the approval-gated tools, which §5.6 shipped as a runtime-side
concern the capability cannot and need not see. The capability itself needs no
`middleware()` hook (HITL handling under §5.6 option B lives in the runtime's
existing middleware), which is why it declares
`execution_models=("react","graph")` rather than misusing the ReAct-only flag.
It is designed for ReAct agents; Graph authors should call
`context.invoke_agent` directly.

> **Rule for anyone extending this:** the description may contain values that
> vary by *execution context* (depth, config, user) but never values that vary
> *per turn* (timestamps, counters, remaining budget). Tool schemas sit at the
> very front of the prompt; churning them invalidates the KV cache for the whole
> conversation. Everything injected today is byte-identical across the turns of
> one conversation.

### 6.4 Parallelism is already real

LangGraph's `ToolNode` runs every tool call in one assistant message
concurrently (`langgraph/prebuilt/tool_node.py`, the `asyncio.gather` in
`ToolNode._afunc`). Several
`run_subagent` calls emitted in one message therefore run **in parallel** today.

What the POC lacks is interleaving, not parallelism: the parent blocks until the
slowest child returns, and the user cannot send a message meanwhile.

The description tells the parent to batch independent work into one message.

Operational note: N children are N full agent turns running concurrently in one
pod, sharing model clients and connection pools. This is hot-path work —
`fred-performance-reviewer` is mandatory before it ships.

### 6.5 Result

Shipped 2026-09-03 (#2529): the tool returns `content_and_artifact` with a
`ToolInvocationResult` carrying the child's text plus its `sources` and
`ui_parts`, and the content cap refuses an over-long answer rather than
truncating it. What and why:
[`../design/RUNTIME-EXECUTION-CONTRACT.md`](../design/RUNTIME-EXECUTION-CONTRACT.md)
§8.66.

**Still open — one observation, not a design question.** A child renders into
the parent's turn, and ownership / duplicate rendering could only be settled by
watching it happen. Code analysis predicts each part renders once and persists
once, under the parent's exchange, with a latent double-render if anything ever
renders parts on a tool-result row; the predictions and their file references
are on [#2529](https://github.com/ThalesGroup/fred/issues/2529), where the POC's
answer belongs. Nothing to decide here until then.

### 6.6 Errors

`LocalRegistryAgentInvoker` currently handles `final`, `assistant_delta` and
`node_error` but **not `execution_error`** (`agent_app.py:668-695`). A child that
raises ends its stream with no `final`, and the caller receives `is_error=True`
with an **empty message**. The runtime feature audit already flags this; this
capability would be its first heavy user, so the fix belongs here: map
`execution_error` to an error result carrying the actual message.

### 6.7 System-prompt override on `AgentInvocationRequest`

`AgentInvocationRequest` gains an optional `system_prompt: str | None`.
When set, it replaces layer 1 of the callee's composed prompt (§5.2);
layers 2–6 are still runtime-owned and cannot be removed by a caller.

**Decided 2026-09-03: the field is public, and the widening is accepted.**
Any Graph node that calls `context.invoke_agent` can now run any registered
callee with its authored template replaced, guardrails kept. Graph agents are
written by developers who own both sides of that call; the contract entry in
`RUNTIME-EXECUTION-CONTRACT.md` §14 must say this in words so it is a
documented power, not a surprise. A private channel was ruled out: the tool
reaches the invoker only through `AgentInvokerPort.invoke(request)`, and a
second method would be the second invocation path §2 rejects.

## 7. Token accounting

Child turns emit **no** `agent.turn_completed` today — that metric is emitted
only from `_stream`, which the invoker bypasses. Sub-agent spend would be
invisible, not double-counted.

The numbers exist and are thrown away: token usage rides the `final` event's
`token_usage` field (`contracts/runtime.py:327`), and the invoker reads only
`content` from that payload.

Therefore:

1. `AgentInvocationResult` gains `token_usage` (additive).
2. The capability emits **`agent.subagent_turn_completed`** through
   `ctx.services.kpi_writer`, with the child's tokens as quantities and the
   **parent's** `session_id`, `agent_instance_id` and `exchange_id` plus
   `invocation_depth` as dims.

A separate metric, not folded into the parent's turn: per-child attribution is
what makes a runaway sub-agent diagnosable, and aggregation can always sum two
metrics while a folded number can never be split. The accepted cost is that any
query reading `agent.turn_completed` alone under-counts — so the metric ships
**with** its Grafana panel and an `OBSERVABILITY-AND-AUDIT.md` note, per the
hot-path checklist.

## 8. Change inventory

Tier 1 (§13) is split into five sub-issues, playable after the first one:
#2525 ships the tool end to end with prompt mode A, then #2526 (HITL), #2527
(prompt mode decision), #2528 (token accounting) and #2529 (`sources` /
`ui_parts` + fan-out performance review) land on top of it in any order.

Slice 1 (#2525) is shipped — what it built is `RUNTIME-EXECUTION-CONTRACT.md`
§8.63 and `capabilities/AUTHORING.md`. What is left to build:

| File | Change | Issue |
| ---- | ------ | ----- |
| `fred_sdk/contracts/context.py` | `system_prompt` override on `AgentInvocationRequest` (§6.7) | #2527 |
| `fred_sdk/contracts/context.py` | `token_usage` on `AgentInvocationResult`, populated by the invoker | #2528 |
| `fred_sdk/contracts/context.py` | `sources`/`ui_parts` populated by the invoker | #2529 |
| `fred_runtime/react/middleware/hitl.py`, `frame.py` | depth ≥ 1 behaviour of §5.6 (hide gated tools; error result instead of `interrupt()`) | #2526 |
| `OBSERVABILITY-AND-AUDIT.md` | `agent.subagent_turn_completed` + its Grafana panel | #2528 |

## 9. Alternative considered — `TeamAgent`

Fred's existing multi-agent concept is `TeamAgent`: a Graph agent with
`sequential` / `dynamic` / `route` modes and a coordinator that dispatches to
**named, pre-registered** members.

Not the answer here, for three reasons. It is Graph-only, so no ReAct agent can
use it. Its members are a fixed roster chosen at authoring time, not work
decomposed at runtime by the model. And its coordinator owns the decomposition,
whereas the point of this feature is that the *parent itself* decides what to
delegate, mid-reasoning, in its own words.

They are complementary: `TeamAgent` composes *different* agents by design;
`run_subagent` composes *the same* agent against different prompts.

## 10. Known limitations

- **SSE goes silent** for the whole child run. There is no backend keepalive;
  the last frame is the parent's `tool_call`. Any intermediary with an idle-read
  timeout drops the connection and the user sees a stalled chat with no `final`.
  Deferred to the UI pass (§11.3) — it will look like a hang in the first demo
  with a slow child.
- **No timeout.** A runaway child hangs the parent's turn until something
  upstream kills the connection. Accepted: a wall-clock cap is a statement about
  the transport, not about the agent, and it becomes irrelevant under §11.1.
  `max_steps` would not help — it is Graph-only; the ReAct loop never reads it.
- **Fan-out unbounded by default** — accepted, see §5.5.
- **MEMORY-02 / MEMORY-06 stay open** for Graph and `TeamAgent` callers.
- **#1859 untouched.** This capability never sets `InvocationScope`, so the
  widening bug is not on its path. Recorded here because a reviewer will ask.

## 11. Deferred, with the direction recorded

### 11.1 Async children and follow-up messaging

The target is background children with the parent notified on completion, and a
tool for the parent to message a running or finished child — asking for
precision rather than re-running it.

That requires the state this POC deliberately drops: a child that can be
messaged must be resumable, so §5.3 must be revisited (either a fresh session id
per child, or MEMORY-02's `checkpoint_ns` done properly). It also reopens what
happens when a user sends a message while children are still working.

Doing this after the POC is cheap; §6.4 means parallelism is not what we are
waiting for.

### 11.2 Choosing a model per child

Orchestrating mixed models is a first-class goal — planning with a fast model
and delegating implementation to a stronger one is the workflow this feature
exists to support. Deferred for scope, not for doubt.

Design, for whoever builds it:

- The argument is an **enum of the models this user may use, in this team**,
  built per turn in `tools()` (which already runs per turn), so it is
  user-specific and cache-stable.
- The set comes from a new `RuntimeServices` port returning the turn's
  *selectable chat profiles* — after the platform binding is applied, not the
  raw ReBAC set. If a platform admin has pinned one model for compliance, the
  enum collapses to one entry and the argument disappears by §6.2, needing no
  new precedence level.
- `CapabilityContext` carries no model information today; that port is the
  missing piece.
- The chosen value is threaded privately, like depth.
- Enum values are model capability ids, display names from
  `CapabilityCatalogEntry.name`. Note `model_capability_id` normalises
  characters and is **not reversible** into its `(provider, name)` pair — do not
  try to split it.

Cost exhaustion is explicitly **not** a reason to withhold this: a user who
wants to burn tokens can already loop ordinary turns. Accountability belongs in
a usage/quota surface, not in a per-feature restriction.

### 11.3 UI

One tool-call line, opening when the child starts and closing when it returns,
is enough for the POC. Showing what a sub-agent is doing — and the keepalive
that makes a long child survive an ingress — belong to the same later pass.

## 12. Open questions for review

Closed 2026-09-03: `ui_parts` stays (§6.5); fan-out stays unbounded (§5.5);
`max_depth` default 3 / ceiling 5 stands; HITL handling lives in
`FredHitlMiddleware` (§5.6); the public `system_prompt` override and the
caller power it grants are accepted (§6.7).

1. **Prompt mode** — R (replace) or A (append), §5.2. The only remaining
   open question. Both are evaluated in the POC; the override field ships
   either way, since mode R cannot be tried without it.

## 13. Delivery tiers (decided 2026-09-03)

Three tiers. Only tier 1 is specified by this RFC and ticketed; the RFC must
be completed (or a side RFC written) for a higher tier **before** its tickets
are cut — §11 records direction, not design.

| Tier | Content | Spec status | Tickets |
| ---- | ------- | ----------- | ------- |
| 1 — playable POC | §5–§7: the tool, same-agent children, depth, HITL, prompt mode, token accounting, `sources` / `ui_parts` | this RFC | #2525 → #2526, #2527, #2528, #2529 |
| 2 — observability UI | SSE keepalive during child runs (§10); child activity nested under the parent's tool-call line, which needs a forwarded child-event shape; sub-agent spend on the analytics page (§11.3) | not written | none until spec'd |
| 3 — async and kinds | background children with completion notification and follow-up messaging (§11.1, opens child state — §5.3 revisited); admin-defined sub-agent kinds such as a "searcher" (§6.2 `kind`), which depends on the prompt-mode decision of #2527; per-child model choice (§11.2) | not written (§11.1 and §11.2 give direction only) | none until spec'd |
