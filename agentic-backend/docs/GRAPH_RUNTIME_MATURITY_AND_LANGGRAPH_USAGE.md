# Graph Runtime Maturity And Remaining LangGraph Usage

Status: active assessment, reliable enough for current v2 graph scope

## Why this note exists

This note records a recurring and legitimate question:

> If Fred v2 graph agents moved so far away from LangGraph, is the runtime still
> robust?

The short answer is:

- yes for the graph use cases Fred is deliberately targeting now
- no if the expectation is "a full generic workflow engine with all of
  LangGraph's maturity surface"

That distinction is important.

## What Fred graph agents still use from LangGraph

For v2 graph agents, the dependency is now quite small.

Main remaining LangGraph usage:

- checkpoint data model
  - `Checkpoint`
  - `CheckpointMetadata`
  - `empty_checkpoint`
- checkpointer contract compatibility
  - saver shape used by Fred's SQL-backed checkpointer
- session/chat resume compatibility nearby
  - `Command` still appears in the session bridge layer, not in graph execution

What Fred graph runtime no longer delegates to LangGraph:

- graph execution
- node dispatch
- business routing
- tool invocation flow
- HITL pause/resume semantics
- final-state carry-over between turns
- runtime event emission

So the graph runtime is now mostly Fred-owned.

## Why that separation is not reckless

Fred is not trying to beat LangGraph at being a general graph framework.
Fred is trying to own the parts that matter at platform level:

- governed human approval
- durable business pause/resume
- conversation continuity across turns
- typed structured outputs
- inspectable, stable runtime behavior

Those are not just workflow-engine details. They are product/runtime concerns.

That is why it is reasonable for Fred to own graph execution semantics more
directly.

## What already looks robust

For the current v2 graph scope, the runtime is in a good place.

Things that already look solid:

- explicit graph authoring contract
- typed node inputs and outputs
- durable checkpoint persistence
- replay-safe resume with `checkpoint_id`
- last completed state carry-over
- typed tool invocation
- typed UI outputs such as links and maps
- session bridge integration with the existing chat stack

This is enough to support a real business workflow such as the postal tracking
graph demo, not just a diagram exercise.

## What is intentionally not claimed yet

Fred graph runtime should **not** be presented as a full replacement for all of
LangGraph's generic engine surface.

Things that are not yet the point:

- rich parallel branch execution
- subgraph composition
- advanced generic retry/backoff policy models
- checkpoint/state migration tooling across graph versions
- broad cancellation and scheduling semantics
- ecosystem-level workflow helper libraries

Those may matter one day, but they are not the bar Fred needs to clear in order
to have a strong business graph runtime now.

## The right way to judge maturity

The right question is not:

> Does Fred graph runtime already do everything LangGraph can do?

The better question is:

> Is Fred graph runtime robust for the kinds of business workflows Fred wants to
> own as a governed platform?

Today, the answer is:

- yes for controlled, branchy, HITL-aware business workflows
- no for "generic workflow engine for any graph someone can imagine"

That is a healthy boundary.

## Practical bottom line

Fred graph runtime is now:

- strong enough to be taken seriously for current business graph agents
- intentionally narrower than LangGraph
- more platform-owned than framework-owned

That is not a weakness by itself.

It only becomes a problem if Fred starts pretending it has already built a
general workflow framework. That would be premature.

## Observability Reality (Langfuse)

Now that graph execution is Fred-owned, Langfuse visibility depends on Fred span
instrumentation quality.

What this means concretely:

- we no longer get automatic “native LangGraph engine internals” for free
- we do get a stable Fred span taxonomy:
  - `v2.graph.node`
  - `v2.graph.model`
  - `v2.graph.tool`
  - `v2.graph.runtime_tool`
  - `v2.graph.await_human`
  - `v2.graph.publish_artifact`
  - `v2.graph.fetch_resource`
- we get Fred metadata for filtering:
  - `agent_name`, `team_id`, `user_name`, `fred_session_id`, etc.

So the trade-off is explicit:

- less framework-native introspection surface
- more platform-controlled and consistent business tracing

If a trace cannot explain latency breakdown, that is a Fred instrumentation
issue to fix in runtime, not an unavoidable limit.

## Pros / Cons For Reviewers

Pros in the current state:

- graph authoring stays focused on business nodes and routes
- runtime semantics (HITL/checkpoint/session continuity) are explicit and testable
- observability contracts can be improved once for every graph agent

Cons to keep in mind:

- runtime team must maintain tracing coverage and naming discipline
- generic workflow-engine features still remain intentionally narrower than LangGraph
- regressions in runtime instrumentation can affect every graph agent at once

The right governance stance is:

- accept this ownership model
- keep strict regression tests and debug playbooks around it
- treat observability gaps as release-blocking quality issues

## One-line summary

Fred v2 graph runtime is robust for the graph workflows Fred currently wants to
support, while still being intentionally much narrower than LangGraph as a
general engine.
