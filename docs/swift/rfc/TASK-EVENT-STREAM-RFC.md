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

All long-running operations emit this model. `kind` is a `Literal` discriminator; `detail` is typed per variant. FastAPI emits an OpenAPI `oneOf` with `discriminator.propertyName: "kind"` — codegen produces a proper TypeScript union.

```python
# libs/fred-core/fred_core/tasks/models.py

from __future__ import annotations
from enum import Enum
from datetime import datetime
from typing import Annotated, Literal, Union
from pydantic import BaseModel, Field

class TaskState(str, Enum):
    pending    = "pending"
    running    = "running"
    cancelling = "cancelling"   # cancel requested, cooperative shutdown in progress
    succeeded  = "succeeded"    # terminal
    failed     = "failed"       # terminal
    cancelled  = "cancelled"    # terminal

# ── per-kind detail models (see §2.5 for full definitions) ───────────────────

class MigrationDetail(BaseModel):
    step_id:   str
    processed: int
    total:     int
    failed:    int

class IngestionDetail(BaseModel):
    processed:   int
    total:       int
    failed:      int
    preview:     int
    vectorized:  int
    sql_indexed: int

# ── shared base (never used directly as an API type) ─────────────────────────

class _TaskEventBase(BaseModel):
    task_id:   str
    state:     TaskState
    seq:       int           # monotone per task_id — used for ordering and SSE replay
    timestamp: datetime
    progress:  float | None  # 0.0–1.0; None = indeterminate (UI shows pulse bar)
    step:      str | None    # human-readable label of the current step
    error:     str | None    # populated only when state == failed

# ── per-kind variants ────────────────────────────────────────────────────────

class MigrationTaskEvent(_TaskEventBase):
    kind:   Literal["migration"] = "migration"
    detail: MigrationDetail | None = None

class IngestionTaskEvent(_TaskEventBase):
    kind:   Literal["ingestion"] = "ingestion"
    detail: IngestionDetail | None = None

class TaskLogDetail(BaseModel):
    level: Literal["info", "warn", "error"]
    message: str

class TaskLogEvent(_TaskEventBase):
    kind:   Literal["log"] = "log"
    detail: TaskLogDetail

TaskEvent = Annotated[
    Union[MigrationTaskEvent, IngestionTaskEvent, TaskLogEvent],
    Field(discriminator="kind"),
]
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

### 2.3 `IScheduler` — a new narrow execution-dispatch interface in `fred-core`

`IScheduler` is a **new, thin interface** for activity execution dispatch only: asyncio vs Temporal. It does **not** replace knowledge-flow's `BaseScheduler`, which owns ingestion-specific domain orchestration (workflow registration, per-user last-workflow tracking, progress computation, `start_document_processing`, etc.) and must stay in knowledge-flow unchanged.

The distinction:
- `IScheduler` answers "which backend runs this activity?" — generic, belongs in `fred-core`.
- `BaseScheduler` answers "how do I orchestrate an ingestion workflow?" — domain-specific, stays in knowledge-flow.
- `PurgeQueueStore` is a DB-backed persistence layer (enqueue / list_due / mark_done), not a scheduler; it is not touched by this RFC.

The existing `SchedulerBackend` enum and `TemporalClientProvider` already in `fred-core` are the kernel of this interface.

```python
# libs/fred-core/fred_core/tasks/scheduler.py

from typing import Protocol, Callable, Awaitable
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

**Seam clarification.** New consumers (migration activities in P2) use `IScheduler` directly — they have no existing orchestration layer. Knowledge-flow's `InMemoryScheduler` and `TemporalScheduler` already implement the same dispatch logic; in P3 they are refactored to delegate that dispatch to `IScheduler` internally, while `BaseScheduler`'s public API is left intact. No caller of `IngestionTaskService` / `BaseScheduler` changes in P1 or P2.

### 2.4 Activity design rules

Every activity — ingestion, lifecycle, migration — must follow these rules regardless of which scheduler runs it. This is what makes memory ↔ temporal substitution safe.

| Rule | Reason |
|---|---|
| Serializable `params` and return type (Pydantic) | Temporal serialisation requirement; also makes memory-mode testable without mocks |
| Idempotent where possible | Temporal may retry; re-running migration must not duplicate rows |
| Call `activity.heartbeat()` periodically for long-running steps | Temporal uses this as the liveness signal; without it the activity is presumed dead and retried |
| Progress via `ctx.emit()` only — never directly to SSE | Works in both scheduler modes |

**What activities are free to do.** Activities run outside Temporal's replay mechanism — Temporal re-executes them fresh on retry rather than replaying a recorded history. Activity code may freely use `datetime.now()`, make database writes, call external APIs, and produce side effects. Idempotency (row 2) handles the retry consequence; it does not restrict what I/O activities perform.

**Where workflow determinism constraints apply.** The `TemporalScheduler` wraps each activity in a thin Temporal workflow. That wrapper — not the activity function — must follow Temporal's workflow determinism rules: no `datetime.now()` (use `workflow.now()`), no direct I/O, no non-deterministic branching. Implementers writing activity functions do not need to think about this.

An activity receives an `ActivityContext` injected by the scheduler:

```python
@dataclass
class ActivityContext:
    task_id: str
    emit:      Callable[[TaskEvent], Awaitable[None]]  # delegates to IEventBus.publish
    heartbeat: Callable[[], None]                      # no-op in MemoryScheduler; calls temporalio.activity.heartbeat() in TemporalScheduler
```

This keeps activity code portable: it calls `ctx.heartbeat()` on a tight inner loop without knowing which scheduler is running.

### 2.5 Per-kind models and the codegen rule

`MigrationDetail` and `IngestionDetail` are defined in §2.1 and live in `fred_core/tasks/models.py`. `StartMigrationParams` / `StartIngestionParams` are defined in §2.7. All models are in `fred-core` — backends import them; backends do not define their own.

`TaskLogEvent` is the typed event used for scrollback lines in the UI. It carries only `level + message` in P1. This is intentionally minimal: enough for `BatchStepCard` to render useful logs without introducing a second generic metadata channel.

**Adding a new `kind` requires all of the following in a single change:**

1. New `*Detail` model in `fred_core/tasks/models.py`
2. New task event variant: `class *TaskEvent(_TaskEventBase)` with `kind: Literal["<kind>"]`
3. New `Start*Params` + `Start*Request` model (see §2.7 pattern)
4. Extension of the `TaskEvent` and `StartTaskRequest` unions
5. OpenAPI regeneration (`make openapi`)
6. Frontend codegen regeneration (`make codegen`)

Never bypass this by widening `detail` back to `dict | None` or `params` to `Any`. The contract discipline here matches the rest of the migration: if a frontend type is missing, strengthen the source model and regenerate — do not hand-write a parallel DTO.

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
  team_id     text,                         -- team scope; NULL for platform-level tasks (e.g. migration)
  created_at  timestamptz   NOT NULL,
  updated_at  timestamptz   NOT NULL
)
```

**Two tables are required together — both mandatory in P1:**

`task_run` is the current-state summary (one row per task, updated in place). It answers "what is the task's current status?" cheaply without scanning history.

`task_event_log` is the append-only event journal (one row per emitted `TaskEvent`). It is the source of truth for replay. Without it, `Last-Event-ID` is meaningless — the server cannot reconstruct intermediate events after a disconnect, making the SSE reliability contract false.

```sql
task_event_log (
  id          bigserial     PRIMARY KEY,
  task_id     uuid          NOT NULL REFERENCES task_run(task_id),
  kind        text          NOT NULL,       -- denormalised from task_run; needed to deserialise detail jsonb on replay
  seq         integer       NOT NULL,
  state       text          NOT NULL,
  progress    float,
  step        text,
  detail      jsonb,
  error       text,
  emitted_at  timestamptz   NOT NULL,
  UNIQUE (task_id, seq)
)
```

`kind` is denormalised from `task_run` so the replay path can deserialise `detail` into the correct Pydantic variant (`MigrationDetail`, `IngestionDetail`, `TaskLogDetail`) without a JOIN. It must be consistent with `task_run.kind`; the write path sets both in the same transaction.

On reconnect: the endpoint queries `task_event_log WHERE task_id = ? AND seq > ?` ordered by `seq`, streams those rows, then resumes the live bus subscription. If the task is already terminal when the client connects, the final event is replayed immediately from the log and the connection is closed.

### 2.7 HTTP endpoints (both backends)

Three endpoints, identical contract in both backends. Protected by the caller's existing auth layer (platform owner for control-plane admin tasks; authenticated user for knowledge-flow ingestion tasks).

**Typed request body** — `POST /tasks` uses a discriminated union so `params` has a schema per `kind`:

```python
# libs/fred-core/fred_core/tasks/models.py (continued)

class StartMigrationParams(BaseModel):
    step_id: Literal[
        "preflight", "copy_tables", "personal_teams",
        "migrate_agents", "validate"
    ]
    dry_run: bool = False

class StartIngestionParams(BaseModel):
    resource_ids: list[str]
    profile: IngestionProcessingProfile = IngestionProcessingProfile.MEDIUM

class StartMigrationRequest(BaseModel):
    kind:   Literal["migration"] = "migration"
    params: StartMigrationParams

class StartIngestionRequest(BaseModel):
    kind:   Literal["ingestion"] = "ingestion"
    params: StartIngestionParams

StartTaskRequest = Annotated[
    Union[StartMigrationRequest, StartIngestionRequest],
    Field(discriminator="kind"),
]
```

```
POST   /api/v1/tasks
       Body: StartTaskRequest   (oneOf discriminated by kind)
       → 202  { task_id: str }
       → No generic duplicate-task detection in P1

GET    /api/v1/tasks
       Query: ?scope=platform|team  (default: platform)
              ?team_id=<id>         (required when scope=team)
              ?kind=<kind>          (optional filter)
              ?state=<state>        (optional filter)
       → 200  { tasks: TaskSummary[] }
       → 403  if caller lacks visibility for the requested scope (see §2.8)
       TaskSummary: { task_id, kind, state, progress, step, error,
                      created_by, team_id, created_at, updated_at }
       → No event history; for live events use the SSE endpoint below

GET    /api/v1/tasks/{task_id}/events
       → text/event-stream      (each data: line is a serialised TaskEvent)
       → Replays task_event_log WHERE seq > Last-Event-ID, then streams live
       → Terminal state closes the connection

POST   /api/v1/tasks/{task_id}/cancel
       → 202  (idempotent; no-op if already terminal)
       → 404  if task_id not found
       → 409  if the task kind does not support cancellation
```

`POST /tasks` creates the `task_run` row, calls `scheduler.submit(...)`, and returns immediately. It never streams. This ensures a browser reconnect can never accidentally re-trigger the operation.

`GET /tasks` is a lightweight poll for dashboard surfaces. It returns current state only — no event history and no SSE. Callers that need live updates open `GET /tasks/{task_id}/events` per task after discovering task IDs from this list.

**Cancellation scope in OPS-04.** The endpoint is generic because future task kinds may support cooperative cancellation. Migration tasks in P2 do not need to implement cancellation; they may return `409` from `POST /cancel`. The cockpit therefore hides `CancelButton` for migration tasks rather than surfacing a button that immediately fails.

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
- Overall status header: `N / 5 steps complete`

For P2 migration tasks, the cockpit does not show `CancelButton`. The generic cancel endpoint exists for future task kinds, but migration steps are treated as non-cancellable in this phase.

---

## 4. Frontend components

The UI investment is designed for reuse. `ProgressBar` and `useTaskStream` are consumed by the cockpit today and by knowledge-flow ingestion panels in the next phase.

### New hook

```typescript
// apps/frontend/src/rework/hooks/useTaskStream.ts
// All types imported from generated controlPlaneOpenApi.ts — never hand-written.

function useTaskStream(taskId: string | null): {
  state:    TaskState | null
  progress: number | null      // null → indeterminate
  step:     string | null
  error:    string | null
  event:    TaskEvent | null   // full typed current event; narrow by event.kind to access detail
  events:   TaskEvent[]        // full history, ordered by seq
}
```

`TaskEvent` in the generated types is the TypeScript union `MigrationTaskEvent | IngestionTaskEvent | TaskLogEvent`. Callers narrow with `if (event.kind === 'migration')` to get `event.detail` typed as `MigrationDetail`, `if (event.kind === 'log')` to get `TaskLogDetail`, etc. No `Record<string, unknown>` assertion is needed or acceptable.

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
                   consumes useTaskStream(taskId)
```

`BatchStepCard` is generic, but the consumer decides whether to render cancel affordances. In P2 `/admin/cockpit`, migration tasks omit `CancelButton`.

---

## 5. Impact on existing code

### `libs/fred-core`

**Add** `fred_core/tasks/` module: `models.py`, `bus.py`, `scheduler.py`.  
`SchedulerBackend` enum and `TemporalClientProvider` already present — incorporate into the new module.

### `apps/knowledge-flow-backend`

**`BaseScheduler` public API is not changed in P1 or P2.** It owns ingestion-domain orchestration (per-user last-workflow tracking, progress computation from metadata stages) which has no counterpart in the generic `IScheduler`.

**P3 only — internal refactor of dispatch.** `InMemoryScheduler` and `TemporalScheduler` both contain asyncio / Temporal dispatch logic that duplicates what `IScheduler` will provide. In P3, that dispatch is extracted and delegated to `IScheduler`; the rest of `BaseScheduler` is left intact. This is an internal implementation change — `IngestionTaskService` callers see no difference.

**P3 — replace poll-based progress.** `record_workflow_status` and `record_current_document` activities are updated to emit `TaskEvent` to `IEventBus`. `get_progress()` on `BaseScheduler` is deprecated (not deleted) once the SSE endpoint is available. `ProcessDocumentsProgressResponse` is kept for backwards compatibility until all UI callers migrate to `useTaskStream`.

**Add** `GET /api/v1/tasks/{task_id}/events` SSE endpoint.  
**Add** `task_run` + `task_event_log` Alembic migration to `knowledge_flow` database.  
**Existing `sched_workflow_tasks` table** is superseded by `task_run`; kept until all callers are migrated.

### `apps/control-plane-backend`

**Add** `control_plane_backend/tasks/` (thin wiring layer to fred-core).  
**Add** `control_plane_backend/migration/` with five step activities. These use `IScheduler` directly — there is no existing orchestration layer to adapt.  
**`PurgeQueueStore` is not touched.** It is a DB-backed persistence layer (enqueue / list_due / mark_done) for the purge lifecycle, not a scheduler. The `LifecycleManagerWorkflow` activities may emit `TaskEvent` in a future phase but that is out of scope for OPS-04.  
**Add** `task_run` + `task_event_log` Alembic migration to `fred_swift` database.  
**Add** frontend cockpit page and new atoms/molecules.

### Frozen contracts

`RUNTIME-EXECUTION-CONTRACT.md` — no changes. Task endpoints are product/admin
surface, not execution surface.

`CONTROL-PLANE-PRODUCT-CONTRACT.md` — updated in the same change as this RFC. A dated entry (§11, OPS-04, 2026-06-04) was added documenting the three `/api/v1/tasks*` endpoints, their ownership (control-plane product surface), and the `task_run` + `task_event_log` tables.

---

## 6. Phased delivery

| Phase | Scope | Outcome |
|---|---|---|
| **P1 — Infrastructure** | `fred-core` tasks module; `IEventBus` (Memory + Postgres); `IScheduler` lifted; `task_run` (with `team_id`) + `task_event_log` Alembic migrations; four HTTP endpoints in both backends (`POST /tasks`, `GET /tasks`, `GET /tasks/{id}/events`, `POST /tasks/{id}/cancel`) | Generic infrastructure available; no UI yet |
| **P2 — Migration cockpit + delete-user** | Five migration activities; delete-user activity (control-plane); cockpit page `/admin/tasks`; `BatchStepCard`, `ProgressBar`, `useTaskStream`; team activity view `/settings/team/activity` | Migration and delete-user runnable from UI with live progress |
| **P3 — Knowledge-flow migration** | Keep `BaseScheduler` public API; delegate backend dispatch internally to `IScheduler`; replace poll-based progress with `TaskEvent`; ingestion panels consume `useTaskStream` | Live ingestion progress in UI; `sched_workflow_tasks` deprecated |

P1 and P2 can be developed in parallel by separate tracks once P1 interfaces are agreed.

---

## 7. Task visibility scopes

The `team_id` column on `task_run` is the single field that drives all visibility
rules. All scoping is enforced server-side; the frontend never filters client-side.

### 7.1 Scope values

| `team_id` value | Meaning |
|---|---|
| `NULL` | Platform-level task — not owned by any team (e.g. migration steps) |
| `"personal-{uid}"` | Task scoped to one user's personal team (e.g. document ingestion) |
| `"<team-id>"` | Task scoped to a regular team (e.g. delete-user for a team member) |

Every activity is responsible for setting `team_id` when it creates the
`task_run` row. Platform-level activities (migration) leave it `NULL`.

### 7.2 Authorization rules for `GET /api/v1/tasks`

| Caller role | `?scope=platform` | `?scope=team&team_id=X` |
|---|---|---|
| Platform admin | All tasks (any `team_id`, including NULL) | All tasks for team X |
| Team admin (owner/manager of team X) | 403 | Tasks where `team_id = X` |
| Regular team member | 403 | 403 |

A platform admin using `scope=team` sees exactly what the team admin sees for
that team — same endpoint, same data, consistent behavior.

### 7.3 Content boundary

Task records contain only operational metadata: state, progress percentage,
step label, error message, `created_by` uid, `team_id`, timestamps, and the
`target` descriptor (type, id, label — e.g. `{ type: "user", id: "…", label:
"alice@example.com" }`).

Task records must never contain:

- document content or titles derived from document content
- conversation text or conversation summaries
- any field from `detail` that is derived from ingested content

Step labels and error messages must be written as operational descriptions
("Vectorising batch 3/10", "Keycloak unreachable") not content descriptions
("Processing 'Q3 financial results.pdf'").

### 7.4 Dashboard surfaces

Three distinct surfaces consume `GET /tasks`, each with a different scope:

| Surface | Route | Scope | Who |
|---|---|---|---|
| Task tray (sidebar) | — | Tasks triggered by `current_user` | Every user |
| Team activity view | `/settings/team/activity` | `scope=team&team_id={current_team}` | Team admin |
| Platform task dashboard | `/admin/tasks` | `scope=platform` | Platform admin |

The task tray is the real-time companion (SSE per task). The team and platform
views are polling dashboards (list + optional drill-down to SSE per task).

---

## 8. Alternatives considered

**WebSocket instead of SSE.** Rejected — the communication is strictly server-to-client (unidirectional). SSE is simpler, HTTP/2 multiplexes it well, and the existing runtime streaming is already SSE.

**Free-form `detail: dict | None`.** Rejected — it weakens OpenAPI/codegen exactly where the frontend needs strongly typed task unions. Per-kind event variants are preferred even though callers narrow on `event.kind`, because that preserves typed `detail` models end to end.

**Polling retained for knowledge-flow.** Rejected — polling requires the client to hold and diff aggregate state. SSE with `seq` is simpler for the client and cheaper for the server under load.

**Single monolithic migration workflow (Option A).** Rejected in favour of five independent tasks (Option B) to allow per-step retry without re-running prior steps.
