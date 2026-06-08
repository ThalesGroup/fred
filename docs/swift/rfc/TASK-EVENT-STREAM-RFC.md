# RFC OPS-04 — Unified Task Event Stream

**ID:** OPS-04  
**Status:** draft  
**Author:** Dimitri Tombroff  
**Date:** 2026-06-04  

---

## 1. Problem

Long-running operations exist in two backends today with no shared model and no real-time progress:

| Backend | Operation | Current mechanism |
|---|---|---|
| knowledge-flow | Document ingestion | Poll-based: client queries metadata to compute aggregate progress |
| control-plane | Session lifecycle purge | Fire-and-forget Temporal workflow, no client visibility |
| control-plane | (planned) kea→swift migration | Not yet implemented |

Three structural gaps result:

1. **No event stream.** Progress is computed by polling metadata state. The UI cannot show live per-item feedback, and there is no persistent history of what happened during a run.
2. **No shared abstraction.** Knowledge-flow's `BaseScheduler` and control-plane's `PurgeQueueStore` are divergent patterns. Neither is in `fred-core`. A third consumer (migration) would produce a third pattern.
3. **No unified task model.** There is no common `task_id`, no common state machine, and no cross-system way to query or cancel a running job.

---

## 2. Proposed Solution

Introduce a **unified task event stream** built on three primitives that live in `fred-core` and are consumed identically by both backends and the frontend.

### 2.1 `TaskEvent` — the single envelope

All long-running operations emit this model. The `kind` field identifies the business domain; `detail` carries kind-specific payload. The envelope never changes across consumers.

```python
# libs/fred-core/fred_core/tasks/models.py

from enum import Enum
from datetime import datetime
from pydantic import BaseModel

class TaskState(str, Enum):
    pending    = "pending"
    running    = "running"
    cancelling = "cancelling"   # cancel requested, cooperative shutdown in progress
    succeeded  = "succeeded"    # terminal
    failed     = "failed"       # terminal
    cancelled  = "cancelled"    # terminal

class TaskEvent(BaseModel):
    task_id:   str
    kind:      str              # "migration" | "ingestion" | "lifecycle" | ...
    state:     TaskState
    seq:       int              # monotone per task_id — used for ordering and SSE replay
    timestamp: datetime
    progress:  float | None     # 0.0–1.0; None = indeterminate (UI shows pulse bar)
    step:      str | None       # human-readable label of the current step
    detail:    dict | None      # kind-specific payload; see §2.5
    error:     str | None       # populated only when state == failed
```

**`seq` and reconnect.** Every emitted event carries a monotone `seq`. The SSE endpoint sets the native `id:` header to `seq`. On reconnect, the browser sends `Last-Event-ID`; the endpoint replays all persisted events with `seq > Last-Event-ID` before resuming the live stream. This is free from the browser and resolves 90 % of reliability issues without application logic.

**Terminal states close the stream.** When the server emits `succeeded`, `failed`, or `cancelled`, it closes the SSE connection. The final state is always persisted so a client that connects after completion receives the terminal event immediately rather than waiting.

**Heartbeat.** The server sends an SSE comment (`: ping`) every 30 s to keep the connection alive through proxies. This is not a `TaskEvent`.

### 2.2 `IEventBus` — the publication abstraction

Activities publish events through this interface. The implementation is chosen at startup; the activity code is identical in both modes.

```python
# libs/fred-core/fred_core/tasks/bus.py

from typing import Protocol, AsyncIterator

class IEventBus(Protocol):
    async def publish(self, event: TaskEvent) -> None: ...
    async def subscribe(self, task_id: str) -> AsyncIterator[TaskEvent]: ...
```

| Implementation | Where | Mechanism |
|---|---|---|
| `MemoryEventBus` | `fred-core` | `asyncio.Queue` per `task_id` — no external services |
| `PostgresEventBus` | `fred-core` | `NOTIFY task:{task_id}` on publish; `LISTEN` on subscribe |

The two implementations are selected alongside the scheduler backend:

```yaml
# configuration_prod.yaml
scheduler:
  backend: memory    # or "temporal"
  # event bus is inferred: memory → MemoryEventBus, temporal → PostgresEventBus
```

### 2.3 `IScheduler` — lifted to `fred-core`

The dual-mode scheduler protocol is promoted from knowledge-flow's `BaseScheduler` to a shared interface in `fred-core`. Both backends implement it. The existing `SchedulerBackend` enum and `TemporalClientProvider` already in `fred-core` become part of this module.

```python
# libs/fred-core/fred_core/tasks/scheduler.py

from typing import Protocol
from pydantic import BaseModel

class IScheduler(Protocol):
    async def submit(
        self,
        task_id: str,
        activity: Callable,
        params: BaseModel,
    ) -> None: ...

    async def cancel(self, task_id: str) -> None: ...
```

| Implementation | Mode | Behaviour |
|---|---|---|
| `MemoryScheduler` | `memory` | Runs activity as an `asyncio` task; cancel via `Task.cancel()` |
| `TemporalScheduler` | `temporal` | Submits Temporal workflow; cancel via `workflow_handle.cancel()` |

### 2.4 Activity design rules

Every activity — ingestion, lifecycle, migration — must follow these rules regardless of which scheduler runs it. This is what makes memory ↔ temporal substitution safe.

| Rule | Reason |
|---|---|
| Serializable `params` and return type (Pydantic) | Temporal serialisation requirement; also makes memory-mode testable without mocks |
| Idempotent where possible | Temporal may retry; re-running migration must not duplicate rows |
| No `datetime.now()` — use injected clock or Temporal's time API | Determinism under replay |
| No side effects outside explicitly managed I/O | Replay safety |
| Progress via `ctx.emit()` only — never directly to SSE | Works in both scheduler modes |

An activity receives an `ActivityContext` injected by the scheduler:

```python
@dataclass
class ActivityContext:
    task_id: str
    emit: Callable[[TaskEvent], Awaitable[None]]  # delegates to IEventBus.publish
```

### 2.5 `detail` payloads by kind

The envelope is fixed; `detail` is free per kind. Documented here for the two initial consumers.

**`kind = "migration"`**
```json
{ "step_id": "migrate_agents", "processed": 47, "total": 120, "failed": 2 }
```

**`kind = "ingestion"`** (replaces current poll-based `ProcessDocumentsProgressResponse`)
```json
{ "processed": 12, "total": 30, "failed": 1,
  "stages": { "preview": 12, "vectorized": 10, "sql_indexed": 8 } }
```

### 2.6 Persistence — `task_run` table

One table per database (`fred_swift` for control-plane, `knowledge_flow` for knowledge-flow). Alembic migration per backend.

```sql
task_run (
  task_id     uuid          PRIMARY KEY,
  kind        text          NOT NULL,
  state       text          NOT NULL,       -- TaskState
  seq         integer       NOT NULL,       -- last emitted seq
  progress    float,
  step        text,
  detail      jsonb,
  error       text,
  created_by  text,                         -- user uuid (audit)
  created_at  timestamptz   NOT NULL,
  updated_at  timestamptz   NOT NULL
)
```

A separate `task_event_log` table (append-only, one row per `TaskEvent`) enables full replay and audit. This table is optional in the initial release but the schema is defined now to avoid a later migration conflict.

### 2.7 HTTP endpoints (both backends)

Three endpoints, identical contract in both backends. Protected by the caller's existing auth layer (platform owner for control-plane admin tasks; authenticated user for knowledge-flow ingestion tasks).

```
POST   /api/v1/tasks
       Body: { kind, params }
       → 202  { task_id }
       → 409  if an identical task is already running (kind + params hash)

GET    /api/v1/tasks/{task_id}/events
       → text/event-stream
       → Replays events with seq > Last-Event-ID, then streams live
       → Terminal state closes the connection

POST   /api/v1/tasks/{task_id}/cancel
       → 202  (idempotent; no-op if already terminal)
       → 409  if task_id not found
```

`POST /tasks` creates the `task_run` row, calls `scheduler.submit(...)`, and returns immediately. It never streams. This ensures a browser reconnect can never accidentally re-trigger the operation.

---

## 3. Migration cockpit — first consumer (`kind = "migration"`)

The migration cockpit is the first net-new feature built on this infrastructure. It is scoped to `kind = "migration"` and platform-owner access only.

### 3.1 Five independent tasks (Option B)

Each migration step is a separately triggerable task. This allows retrying a failed step without re-running prior steps.

| `step_id` | Description | Idempotency |
|---|---|---|
| `preflight` | Verify `fred_swift` schema, count source rows, check OpenFGA reachable | read-only |
| `copy_tables` | Copy `tag`, `metadata`, `resource`, `teammetadata`, `users` verbatim | `INSERT … ON CONFLICT DO NOTHING` |
| `personal_teams` | Create one personal team per Keycloak user via `personal_team_id()` | `INSERT … ON CONFLICT DO NOTHING` |
| `migrate_agents` | Transform `fred.agent` blobs → `fred_swift.agent_instance` using the kea→swift agent map | `INSERT … ON CONFLICT DO UPDATE` |
| `validate` | Run §2.5 checks; emit pass/fail per check as `log`-level detail | read-only |

Step N's `POST /tasks` endpoint returns 409 if step N-1 is not in state `succeeded`. This enforces ordering at the API level, not only in the UI.

### 3.2 Agent mapping table (kea → swift)

Resolved from live catalog inspection. Stored in `control_plane_backend/migration/agent_map.py`.

| kea `definition_ref` | swift `source_agent_id` | `source_runtime_id` |
|---|---|---|
| `v2.react.basic` | `fred.github.assistant` | `fred-agents` |
| `v2.production.sql_analyst` | `fred.github.sql_expert` | `fred-agents` |

### 3.3 Cockpit page

New page in the frontend, visible to platform owners only:

- Route: `/admin/cockpit`
- Five `BatchStepCard` components in dependency order
- One `CancelButton` per running step
- Overall status header: `N / 5 steps complete`

---

## 4. Frontend components

The UI investment is designed for reuse. `ProgressBar` and `useTaskStream` are consumed by the cockpit today and by knowledge-flow ingestion panels in the next phase.

### New hook

```typescript
// apps/frontend/src/rework/hooks/useTaskStream.ts
function useTaskStream(taskId: string | null): {
  state:     TaskState | null
  progress:  number | null   // null → indeterminate
  step:      string | null
  detail:    Record<string, unknown> | null
  error:     string | null
  events:    TaskEvent[]     // full history, ordered by seq
}
```

Owns the SSE connection. Handles reconnect transparently via `Last-Event-ID`.

### New atoms / molecules

```
atoms/
  TaskStateBadge   pending | running | cancelling | succeeded | failed | cancelled
  ProgressBar      animated fill 0–1; null → CSS pulse animation
  LogLine          info / warn / error coloured line

molecules/
  BatchStepCard    TaskStateBadge + ProgressBar + scrollable LogLine list
                   + Run button (disabled if prerequisite not succeeded)
                   + Cancel button (visible when running or cancelling)
                   consumes useTaskStream(taskId)
```

---

## 5. Impact on existing code

### `libs/fred-core`

**Add** `fred_core/tasks/` module: `models.py`, `bus.py`, `scheduler.py`.  
`SchedulerBackend` enum and `TemporalClientProvider` already present — incorporate into the new module.

### `apps/knowledge-flow-backend`

**Migrate** `BaseScheduler` / `InMemoryScheduler` / `TemporalScheduler` to implement `IScheduler`.  
**Replace** poll-based `get_progress()` with `TaskEvent` emission from activities.  
`record_workflow_status` and `record_current_document` activities emit `TaskEvent` to `IEventBus`.  
**Add** `GET /api/v1/tasks/{task_id}/events` SSE endpoint.  
**Add** `task_run` Alembic migration to `knowledge_flow` database.  
**Existing `sched_workflow_tasks` table** is superseded by `task_run`; kept until all callers are migrated.

### `apps/control-plane-backend`

**Add** `control_plane_backend/tasks/` (thin wiring layer to fred-core).  
**Add** `control_plane_backend/migration/` with five step activities.  
**Migrate** `LifecycleManagerWorkflow` activities to emit `TaskEvent`.  
**Add** `task_run` Alembic migration to `fred_swift` database.  
**Add** frontend cockpit page and new atoms/molecules.

### Frozen contracts

No changes to `RUNTIME-EXECUTION-CONTRACT.md` or `CONTROL-PLANE-PRODUCT-CONTRACT.md`. The `/tasks` endpoints are a new surface, not a modification of existing ones.

---

## 6. Phased delivery

| Phase | Scope | Outcome |
|---|---|---|
| **P1 — Infrastructure** | `fred-core` tasks module; `IEventBus` (Memory + Postgres); `IScheduler` lifted; `task_run` Alembic migrations; three HTTP endpoints in both backends | Generic infrastructure available; no UI yet |
| **P2 — Migration cockpit** | Five migration activities; cockpit page; `BatchStepCard`, `ProgressBar`, `useTaskStream` | Migration runnable from UI by platform admin |
| **P3 — Knowledge-flow migration** | Replace `BaseScheduler` with `IScheduler`; replace poll-based progress with `TaskEvent`; ingestion panels consume `useTaskStream` | Live ingestion progress in UI; `sched_workflow_tasks` deprecated |

P1 and P2 can be developed in parallel by separate tracks once P1 interfaces are agreed.

---

## 7. Alternatives considered

**WebSocket instead of SSE.** Rejected — the communication is strictly server-to-client (unidirectional). SSE is simpler, HTTP/2 multiplexes it well, and the existing runtime streaming is already SSE.

**Per-kind event schemas.** Rejected — a separate Pydantic model per `kind` would require the frontend to branch on type. The single envelope with a free `detail` dict keeps the UI fully generic; kind-specific rendering reads from `detail` optionally.

**Polling retained for knowledge-flow.** Rejected — polling requires the client to hold and diff aggregate state. SSE with `seq` is simpler for the client and cheaper for the server under load.

**Single monolithic migration workflow (Option A).** Rejected in favour of five independent tasks (Option B) to allow per-step retry without re-running prior steps.
