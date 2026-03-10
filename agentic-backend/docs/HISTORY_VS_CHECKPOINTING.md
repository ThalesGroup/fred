# History Vs Checkpointing

Status: exploratory design note, needs further thinking

## Why this note exists

Fred v2 now persists both:

- a user-facing conversation history
- a runtime-facing checkpoint stream

It also still keeps a warm per-session in-memory agent cache.

They already share the same SQL infrastructure, but they are still separate
mechanisms. This document explains why that separation currently makes sense,
where the tension really is, and what a more unified future model could look
like.

## The current split

At runtime, Fred currently has three different continuity layers:

- warm in-memory agent cache
- product transcript history
- durable runtime checkpointing

### 1. History store

The history store persists the chat transcript in a product-friendly shape.

Current implementation:
- [postgres_history_store.py](/home/dimi/run/reference/fred/agentic-backend/agentic_backend/core/monitoring/postgres_history_store.py)

It stores things such as:
- `session_id`
- `rank`
- `role`
- `channel`
- `exchange_id`
- `parts_json`
- `metadata_json`

This is the data model used for:
- UI replay
- session history APIs
- debugging conversation content
- metrics and reporting on visible exchanges

### 2. Checkpointer

The checkpointer persists runtime state in an execution-friendly shape.

Current implementation:
- [sql_checkpointer.py](/home/dimi/run/reference/fred/agentic-backend/agentic_backend/core/agents/v2/sql_checkpointer.py)

It stores things such as:
- checkpoint snapshots
- channel blobs
- pending writes
- parent checkpoint lineage

This is the data model used for:
- pause/resume
- durable runtime continuity
- graph carry-over state
- restart tolerance

## The key observation

This observation is valid:

- history is closer to durable conversation truth
- checkpointing is closer to short-term execution continuity

That does not mean checkpoints are useless after a restart. They are still what
the runtime needs to continue correctly. But it does mean they are not the best
source of truth for a user-facing transcript.

## Why they should not simply become one mechanism

At first glance, it is tempting to ask:

- if the runtime stores messages in channels anyway, why not use that as the
  history store too?

The problem is that the two concerns have different invariants.

### History wants

- readable and stable schema
- queryable transcript semantics
- explicit ordering and ranking
- auditability
- UI/API friendliness
- long retention without engine coupling

### Checkpointing wants

- exact resumability
- runtime-engine compatibility
- tolerance for opaque blobs
- parent lineage and versioning
- internal channel state
- freedom to evolve with runtime semantics

So while both live in SQL, they do not want the same data model.

## Current recommendation

For the current v2 architecture:

- keep the warm cache for hot-session performance
- keep history and checkpointing separate conceptually
- keep sharing the same SQL infrastructure
- do not replace the history store with the checkpointer

This is the cleanest model while the v2 runtime contract is still stabilizing.

## The real tension to keep thinking about

The more important question is not:

- can checkpoints replace history?

It is:

- for which v2 agents do we actually need durable checkpointing on every turn?

That is especially relevant for simple ReAct agents, where:
- history restore already gives a lot of continuity
- runtime cache may still exist in memory
- durable checkpointing can add extra Postgres round trips per exchange

So the likely optimization topic is:
- make ReAct checkpoint policy more selective
- not collapse history and checkpointing into one store

## Option C: a more ambitious future direction

The most interesting long-term idea is not “history inside checkpoints”.
It is a deeper redesign:

- one append-only conversation event log
- transcript views derived from it
- runtime state derived from it

In that model:
- history is not a separate handwritten transcript table
- checkpointing is not a separate opaque side channel
- both become projections over a common event stream

That would be a real architectural shift.

Potential benefits:
- one durable source of truth
- cleaner replay semantics
- clearer audit trail
- fewer duplicated persistence responsibilities

Potential costs:
- much bigger redesign
- more complex event and projection model
- migration risk while v2 runtime is still maturing

So this idea is attractive, but it should be treated as:
- future architecture exploration
- not near-term cleanup work

## Practical conclusion

Today:

- keep history store as the product transcript mechanism
- keep checkpointing as the runtime continuity mechanism
- treat ReAct checkpoint policy as the likely optimization frontier

Later, if Fred wants a more unified persistence model, the serious candidate is:

- event-sourced conversation persistence with transcript and runtime state as
  derived views

That is the interesting “Option C”, but it belongs to a later design phase.
