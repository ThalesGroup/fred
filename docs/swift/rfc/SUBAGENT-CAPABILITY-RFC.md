# RFC — Sub-agent Capability: an agent delegates work to fresh-context copies of itself

**Status:** Tier 1 shipped (2026-09-03/04). This RFC has been trimmed to what is
still genuinely open: the prompt-mode evaluation (§2), the fan-out bound (§3),
one POC observation (§4), and the unspecified tiers 2-3 (§8). Everything tier 1
built is recorded in the compact docs, not here —
`../design/RUNTIME-EXECUTION-CONTRACT.md` §8.63-§8.68 and §14 (contract
surface), `../capabilities/AUTHORING.md` (what a capability author needs),
`../platform/OBSERVABILITY-AND-AUDIT.md` §3.1 (the per-child metric), and
`libs/fred-capability-subagent/README.md` (the package itself).
Throughout, a `§8.6x` or `§14` reference is to the execution contract; a bare
single-digit `§N` is a section of this RFC.
**Author:** Florian Muller
**Date:** 2026-09-03 (trimmed 2026-09-04)
**Area:** `fred-sdk` (contracts), `fred-runtime` (invoker, capability block), the `subagent` capability package
**Tracking:** [#2520](https://github.com/ThalesGroup/fred/issues/2520) (parent);
tier 1 landed as #2525 → #2526, #2527, #2528, #2529; fan-out is
[#2531](https://github.com/ThalesGroup/fred/issues/2531)
**Related:** `MULTI-AGENT-MEMORY-HARDENING-RFC.md` (MEMORY-02, MEMORY-06),
`design/MULTI_AGENT_MEMORY.md`, the `add-fred-capability` skill.

---

## 1. Why this exists

A ReAct agent has no way to delegate. Faced with a task that decomposes into
several independent pieces — read five documents and compare them, draft three
variants, investigate four hypotheses — it must do all of it in one linear
message history. Every intermediate result stays in context, the transcript
grows past the point where the model attends to it well, and the pieces run one
after another even when nothing couples them.

Tier 1 answers that with one tool, `run_subagent`, that runs a fresh-context
copy of the calling agent against a prompt the parent writes, on the existing
`invoke_agent` primitive rather than a second invocation path. It is a POC
surface: `ADMIN_GATED`, selected by no agent by default.

## 2. Open — prompt mode: replace or append

`compose_system_prompt` (`react_prompting.py`) builds eight layers. The child
gets:

| Layer | Child |
| ----- | ----- |
| 1. rendered agent template | **replaced** in mode R; kept below the framing in mode A |
| 2. runtime tool descriptions | kept |
| 3. definition guardrails | kept |
| 4. global base output contract | kept |
| 5. tool-failure recovery notice | kept |
| 6. runtime-specific suffixes | kept |
| 7. user-selected context prompts | **dropped** |
| 8. conversation attachments | **dropped** |

Layers 2-6 are runtime-owned invariants; dropping them would break tool use and
output formatting for the tools the child is meant to keep. Layers 7-8 are the
user's conversation context, which the child has no user for. The framing itself
is short and states: this is a sub-agent run, there is no user, do not ask
questions, return the answer as text, and that tools requiring human approval
are unavailable or will refuse.

Both modes ship, selectable per agent on the capability's `prompt_mode` config
(`append` = mode A, the default; `replace` = mode R, which uses the
`AgentInvocationRequest.system_prompt` override, §8.67). **The evaluation itself
is what remains open**, on #2527.

- **Mode R — replace.** Layer 1 becomes framing + the parent's `prompt`. A
  parent template written for a human ("the user will ask you…") cannot mislead
  a child that has no user. Cost: **a child inherits no persona, tone, output
  language or business rule from its parent's template.** A template that says
  "always answer in French" produces children that do not, unless the parent
  restates it in every call — a tax the model will forget.
- **Mode A — append.** Framing first, then the parent's template kept verbatim
  as *inherited instructions*, with the framing stating that there is no user
  and that any "ask the user" instruction in the template does not apply. The
  parent's `prompt` travels as the child's `message` (the user turn). Cost:
  template text that argues with the framing ("greet the user", "end with a
  question") may confuse the child.

Evaluation criteria: output language and persona retention across ≥3 agents
whose templates carry such rules; frequency of the child asking questions or
addressing a user; prompt-token overhead per child. Whichever wins, the layer
table above is updated and **the losing mode is deleted from the code**.

## 3. Open — fan-out is unbounded

Depth bounds height, not width. `max_depth` (default 3, ceiling 5) stops a chain
from recursing, but nothing bounds how many children one assistant message
launches, and they run concurrently in one pod against a shared connection pool.

The original decision accepted this on the premise that
`ToolSelectionPolicy.max_tool_calls_per_turn` already bounded it. **That premise
is wrong twice** (#2525 performance review): the knob is set (12 on five agents,
30 on `platform_ops`), and it maps to a **per-graph-run** limit, so a child — its
own graph run — resets the counter and it bounds nothing across depth. Real
worst case at `max_depth=3` is ~1 900 concurrent agent turns for one user
message, against a 500-connection pool per pod. The per-child content cap has the
same shape: it caps each child, and does not compose across the fan.

**Decision: unbounded for the POC, to be settled with POC data on
[#2531](https://github.com/ThalesGroup/fred/issues/2531).** Two later findings
are data points for it rather than answers: retrying provider 429s (§8.65) buys
patience, not headroom, and every child's `ui_parts` now cross the SSE stream
twice (§8.66), which multiplies by fan-out width.

## 4. Open — one POC observation to confirm

A child renders into the parent's turn. Code analysis predicts each part renders
once and persists once, under the parent's exchange, with a latent double-render
if anything ever renders parts on a tool-result row (§8.66 states both). That is
a prediction about behaviour, settled only by watching it happen; the POC's
answer belongs on [#2529](https://github.com/ThalesGroup/fred/issues/2529).
Nothing to decide here until then.

## 5. Known limitations that stay open

- **SSE goes silent** for the whole child run. There is no backend keepalive;
  the last frame is the parent's `tool_call`. Any intermediary with an idle-read
  timeout drops the connection and the user sees a stalled chat with no `final`.
  Deferred to the UI pass (§6.3) — it will look like a hang in the first demo
  with a slow child.
- **No timeout.** A runaway child hangs the parent's turn until something
  upstream kills the connection. Accepted: a wall-clock cap is a statement about
  the transport, not about the agent, and it becomes irrelevant under §6.1.
  `max_steps` would not help — it is Graph-only; the ReAct loop never reads it.
  Note the observability cost this carries, recorded in
  `../platform/OBSERVABILITY-AND-AUDIT.md` §3.1: a cancelled child emits no
  metric, so the per-child metric is blind to exactly the pathology it would be
  most useful for.
- **A child cannot do work that needs a human decision.** Not a hang risk any
  more (§8.64), but a capability limit that only §6.1's resumable children would
  lift.
- **MEMORY-02 / MEMORY-06 stay open** for Graph and `TeamAgent` callers, which
  reach `invoke_agent` directly and have no bound of their own (§14).
- **#1859 untouched.** This capability never sets `InvocationScope`, so the
  scope-widening bug is not on its path. Recorded because a reviewer will ask.

## 6. Deferred, with the direction recorded

Direction only — none of this is specified. Per §8, a tier-2 or tier-3 ticket
must not be cut until this RFC (or a side RFC) actually specifies it.

### 6.1 Async children and follow-up messaging

The target is background children with the parent notified on completion, and a
tool for the parent to message a running or finished child — asking for
precision rather than re-running it.

That requires the state tier 1 deliberately drops: a child that can be messaged
must be resumable, so the checkpointer-free decision (§8.63) must be revisited —
either a fresh session id per child, or MEMORY-02's `checkpoint_ns` done
properly. It also reopens what happens when a user sends a message while
children are still working.

Parallelism is *not* what we are waiting for: LangGraph's `ToolNode` already runs
one message's tool calls concurrently, so siblings already run in parallel. What
the POC lacks is interleaving — the parent blocks until the slowest child
returns, and the user cannot send a message meanwhile.

### 6.2 Choosing a model per child

Orchestrating mixed models is a first-class goal — planning with a fast model and
delegating implementation to a stronger one is the workflow this feature exists
to support. Deferred for scope, not for doubt.

Design, for whoever builds it:

- The argument is an **enum of the models this user may use, in this team**,
  built per turn in `tools()` (which already runs per turn), so it is
  user-specific and cache-stable.
- The set comes from a new `RuntimeServices` port returning the turn's
  *selectable chat profiles* — after the platform binding is applied, not the
  raw ReBAC set. If a platform admin has pinned one model for compliance, the
  enum collapses to one entry and the argument disappears by the rule below,
  needing no new precedence level.
- `CapabilityContext` carries no model information today; that port is the
  missing piece.
- The chosen value is threaded privately, like depth.
- Enum values are model capability ids, display names from
  `CapabilityCatalogEntry.name`. Note `model_capability_id` normalises
  characters and is **not reversible** into its `(provider, name)` pair — do not
  try to split it.

Cost exhaustion is explicitly **not** a reason to withhold this: a user who wants
to burn tokens can already loop ordinary turns. Accountability belongs in a
usage/quota surface, not in a per-feature restriction.

> **Schema rule both deferred arguments must follow — an argument appears only
> when there is a real choice.** `kind` is implemented but, with `"self"` as its
> only value, is absent from the schema; it appears when an admin can configure
> named kinds. `model` follows the same rule: one usable model, no argument. An
> enum with one legal value costs schema tokens on every turn and gives the model
> a decision it cannot get right or wrong.

### 6.3 UI

One tool-call line, opening when the child starts and closing when it returns, is
enough for the POC. Showing what a sub-agent is doing — and the keepalive that
makes a long child survive an ingress (§5) — belong to the same later pass.

## 7. Alternatives considered and rejected

- **`TeamAgent`** — Fred's existing multi-agent concept: a Graph agent with
  `sequential` / `dynamic` / `route` modes and a coordinator that dispatches to
  **named, pre-registered** members. Not the answer here, for three reasons. It
  is Graph-only, so no ReAct agent can use it. Its members are a fixed roster
  chosen at authoring time, not work decomposed at runtime by the model. And its
  coordinator owns the decomposition, whereas the point of this feature is that
  the *parent itself* decides what to delegate, mid-reasoning, in its own words.
  They are complementary: `TeamAgent` composes *different* agents by design;
  `run_subagent` composes *the same* agent against different prompts.
- **LangChain / `deepagents` sub-agent features** — rejected. A recorded position
  (2026-08-12 operation-concept validation) keeps model and operation routing
  Fred-owned; a naked `create_agent` inside a tool would bypass identity
  delegation, model routing, KPI and tracing.

## 8. Delivery tiers (decided 2026-09-03)

Three tiers. Only tier 1 was specified by this RFC and ticketed; the RFC must be
completed (or a side RFC written) for a higher tier **before** its tickets are
cut — §6 records direction, not design.

| Tier | Content | Spec status | Tickets |
| ---- | ------- | ----------- | ------- |
| 1 — playable POC | the tool, same-agent children, depth, HITL, prompt mode, token accounting, `sources` / `ui_parts` | shipped; recorded in `RUNTIME-EXECUTION-CONTRACT.md` §8.63-§8.68 | #2525 → #2526, #2527, #2528, #2529 |
| 2 — observability UI | SSE keepalive during child runs (§5); child activity nested under the parent's tool-call line, which needs a forwarded child-event shape; sub-agent spend on the analytics page (§6.3) | not written | none until spec'd |
| 3 — async and kinds | background children with completion notification and follow-up messaging (§6.1, reopens child state); admin-defined sub-agent kinds such as a "searcher" (§6.2's schema rule), which depends on the prompt-mode decision of §2; per-child model choice (§6.2) | not written (§6.1 and §6.2 give direction only) | none until spec'd |
