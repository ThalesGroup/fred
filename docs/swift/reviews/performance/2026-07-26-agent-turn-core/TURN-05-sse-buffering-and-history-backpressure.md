# TURN-05 — SSE buffers the full event stream and history persistence has no backpressure

- **GitHub issue:** dedicated issue not yet created
- **Priority:** P2
- **Verdict:** needs-load-test
- **Owner:** unassigned

## Production impact

The streaming route yields each SSE event but also retains every runtime payload
in a per-turn list. After the stream, it launches an untracked background task
that transforms and writes that full payload set to history. There is no bounded
queue, task registry, admission control, or shutdown drain for these writes.

Memory therefore scales with event/tool-result volume, concurrent turns, and
database delay. A slow history database can leave many payload graphs alive
after clients have received `final`.

## Evidence

- `libs/fred-runtime/fred_runtime/app/agent_app.py:2174-2187` appends every
  payload to `collected` while yielding SSE.
- `agent_app.py:2202-2219` calls `asyncio.create_task` for history persistence
  without placing the task in a bounded owner.
- `agent_app.py:1702-1915` computes the next rank, maps payloads into a second
  message collection, and batch-saves them.
- `libs/fred-core/fred_core/history/postgres_history_store.py:180-242`
  batch-upserts the final rows, which is a positive property.
- The design intentionally makes history fail-open and post-stream; it does not
  currently define a capacity or delivery bound.

## Minimal fix direction

Separate transport from persistence with a bounded, lifecycle-owned queue or
write service. Retain only the canonical history projection needed for storage,
not every wire payload. Define overload behavior explicitly: backpressure,
bounded drop with telemetry, or durable handoff.

## Acceptance criteria

- Pending history work and retained bytes have explicit per-pod bounds.
- Shutdown drains or deliberately reports abandoned writes.
- Persistence errors remain fail-open for the response but are observable.
- Event ordering/rank remains correct under two concurrent turns in one session.
- A 200-turn test with large tool results and delayed PostgreSQL records RSS,
  queue depth, dropped/failed writes, and completion lag.

## Decision log

- **2026-07-26:** code shape confirmed; severity remains `needs-load-test`
  because representative payload sizes and database lag were not measured.

## Resolution evidence

Not resolved.
