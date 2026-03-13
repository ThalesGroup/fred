Status: decision note, revisit only if Fred's DB lifecycle changes materially

## Context

Fred v2 now has its own durable checkpoint implementation in
`agentic_backend/core/agents/v2/sql_checkpointer.py`.

We also evaluated the community LangGraph Postgres package:

- dependency: `langgraph-checkpoint-postgres`
- main class of interest: `AsyncPostgresSaver`

This note records the outcome of that evaluation so the topic can be resumed
later without redoing the analysis from scratch.

## Decision

For now, Fred should **keep its own v2 checkpointer implementation** and **not
replace it with `AsyncPostgresSaver`**.

This is not because the community package is weak. It is because it is **not a
clean drop-in fit** for Fred's current platform architecture.

## Short Verdict

- `AsyncPostgresSaver` is a serious implementation.
- It is worth knowing and may be useful later.
- It is **not** a perfect fit for Fred v2 today.
- The current Fred implementation remains the safer choice.

## What Was Evaluated

We looked at the installed package after adding the dependency:

- `langgraph.checkpoint.postgres`
- `langgraph.checkpoint.postgres.aio.AsyncPostgresSaver`

The main question was:

Can Fred v2 replace its own SQL-backed saver with the community Postgres saver
without weakening the current runtime design?

## Why We Are Keeping Fred's Implementation

### 1. Different infrastructure center of gravity

`AsyncPostgresSaver` is **psycopg-native**.

It expects:

- `psycopg.AsyncConnection`
- or `psycopg_pool.AsyncConnectionPool`

Fred is currently **SQLAlchemy-native** for durable backend infrastructure.
Its services share one platform-owned `AsyncEngine` lifecycle through the app
context.

That means the mismatch is not about SQL itself. It is about **who owns the DB
connection lifecycle**.

If Fred adopted `AsyncPostgresSaver` directly, it would likely need:

- a second pool lifecycle just for checkpointing
- separate setup/migration handling
- another place to reason about connection tuning and observability

That is the biggest reason it is not a drop-in replacement.

### 2. Fred's current implementation matches the existing app lifecycle

Fred's saver plugs directly into the shared SQL engine and current storage
helpers. That keeps checkpointing aligned with the rest of the backend
infrastructure.

This is especially valuable while the v2 runtime contract is still settling.

### 3. Fred currently preserves a more uniform local-dev story

The community saver is explicitly Postgres + psycopg oriented.

Fred's current saver was designed so that the same runtime contract works
through the existing Fred storage lifecycle in both:

- production Postgres
- local development fallback

That is not a minor detail. It affects how easily v2 can be exercised and
debugged locally.

### 4. The storage backend is only part of the v2 runtime story

Even with a perfect Postgres saver, Fred would still own important v2 runtime
semantics in its own code, especially for graph agents:

- pending HITL checkpoint meaning
- last completed graph state
- turn-to-turn carry-over behavior

So even if the storage layer changed later, Fred would still keep runtime-level
checkpoint semantics above it.

## What Looked Good In The Community Package

This evaluation was not negative.

`AsyncPostgresSaver` has several strengths:

- real async implementation
- proper Postgres persistence
- good fit for vanilla LangGraph checkpointing
- closer to an async-first posture than the memory saver
- useful as a reference implementation and benchmark

So the package is worth keeping in mind.

## Why This Is Not "Reinventing For No Reason"

Fred did not write its own saver because the ecosystem had nothing.

The ecosystem does have a Postgres saver.

Fred wrote its own because it currently needs a saver that fits:

- Fred's shared SQLAlchemy engine lifecycle
- Fred's current local-dev / production setup model
- Fred's v2 runtime semantics
- Fred's async-only posture for real v2 execution paths

## Current Recommendation

Keep:

- `agentic_backend/core/agents/v2/sql_checkpointer.py`

Do not replace it with:

- `langgraph.checkpoint.postgres.aio.AsyncPostgresSaver`

at least not directly.

## What Could Be Revisited Later

Later, if checkpointing becomes a larger concern, we can revisit one of these
options:

1. Keep Fred's implementation permanently.
2. Wrap `AsyncPostgresSaver` behind a thin Fred adapter.
3. Move Fred checkpointing infrastructure toward a psycopg-native lifecycle.

Today, option 1 is the safest and most coherent.

## Practical Handoff Summary

If a developer picks this topic up later, the starting assumption should be:

- do not attempt a direct swap
- first decide whether Fred still wants checkpointing to remain aligned with
  the shared SQLAlchemy engine lifecycle
- only then evaluate whether a thin adapter around `AsyncPostgresSaver` is
  worth the added complexity

## Final One-Line Summary

`AsyncPostgresSaver` is a good **driver-level Postgres saver**.
Fred currently needs a **platform-level saver aligned with its shared engine
lifecycle and v2 runtime contract**.
