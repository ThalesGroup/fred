# RFC OPS-04 — Unified Task Event Stream

**ID:** OPS-04  
**Status:** confirmed — 2026-06-16  
**Author:** Dimitri Tombroff  
**Date:** 2026-06-04  

---

## 1. Problem

Long-running operations exist across backends with no shared model and no real-time progress:

| Backend | Operation | Current mechanism |
|---|---|---|
| knowledge-flow | Document ingestion | Poll-based: client queries metadata to compute aggregate progress |
| control-plane | Session lifecycle purge | Fire-and-forget Temporal workflow, no client visibility |
| control-plane | kea→swift migration | Net-new |

Three structural gaps: **(1) no event stream** — progress is polled, with no live per-item feedback and no persistent run history; **(2) no shared abstraction** — knowledge-flow's `BaseScheduler` and control-plane's `PurgeQueueStore` are divergent, neither in `fred-core`, and a new consumer would add a third pattern; **(3) no unified task model** — no common `task_id`, state machine, or cross-system query/cancel.

---

## 2. Design

A unified task event stream built on primitives that live in `fred-core` and are consumed identically by all backends and the frontend.

### 2.1 `TaskEvent` — the single envelope

All long-running operations emit this model. `kind` is a `Literal` discriminator; `detail` is typed per variant. FastAPI emits an OpenAPI `oneOf` (`discriminator.propertyName: "kind"`) so codegen produces a proper TypeScript union.

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

# ── per-kind detail models ───────────────────────────────────────────────────

class MigrationDetail(BaseModel):
    step_id: str; processed: int; total: int; failed: int

class IngestionDetail(BaseModel):
    processed: int; total: int; failed: int
    preview: int; vectorized: int; sql_indexed: int

class EvaluationDetail(BaseModel):
    campaign_id: str; completed: int; total: int
    passed: int; failed: int; execution_errors: int; scoring_errors: int

class TaskLogDetail(BaseModel):
    level: Literal["info", "warn", "error"]
    message: str

# ── target descriptor (which object the task operates on) ─────────────────────

class TaskTarget(BaseModel):
    """Carried on every event so the frontend links a task to a row without a lookup."""
    type:  str   # "document" | "user" | "evaluation_campaign" | …
    id:    str   # object's unique identifier (e.g. document_uid)
    label: str   # human-readable label shown in the UI (e.g. filename)

# ── shared base (never an API type directly) ─────────────────────────────────

class _TaskEventBase(BaseModel):
    task_id:   str
    state:     TaskState
    seq:       int           # monotone per task_id — ordering + SSE replay
    timestamp: datetime
    progress:  float | None  # 0.0–1.0; None = indeterminate (UI shows pulse bar)
    step:      str | None    # human-readable label of the current step
    error:     str | None    # populated only when state == failed
    target:    TaskTarget | None = None  # None for platform tasks
    owner:     str | None = None         # uid of the user who triggered the task

# ── per-kind variants ────────────────────────────────────────────────────────

class MigrationTaskEvent(_TaskEventBase):
    kind: Literal["migration"] = "migration";  detail: MigrationDetail | None = None
class IngestionTaskEvent(_TaskEventBase):
    kind: Literal["ingestion"] = "ingestion";  detail: IngestionDetail | None = None
class EvaluationTaskEvent(_TaskEventBase):
    kind: Literal["evaluation"] = "evaluation"; detail: EvaluationDetail | None = None
class TaskLogEvent(_TaskEventBase):
    kind: Literal["log"] = "log";              detail: TaskLogDetail

TaskEvent = Annotated[
    Union[MigrationTaskEvent, IngestionTaskEvent, EvaluationTaskEvent, TaskLogEvent],
    Field(discriminator="kind"),
]
```

**SSE semantics.**
- **`seq` + reconnect.** Each event carries a monotone `seq`, set as the SSE `id:`. On reconnect the browser sends `Last-Event-ID`; the endpoint replays persisted events with `seq > Last-Event-ID`, then resumes live. Free from the browser; no application logic.
- **Terminal closes the stream.** Emitting `succeeded`/`failed`/`cancelled` closes the connection. The terminal event is persisted, so a client connecting after completion receives it immediately.
- **Heartbeat.** An SSE comment (`: ping`) every 30 s keeps the connection alive through proxies (not a `TaskEvent`).

### 2.2 `IEventBus` — publication abstraction

Activities publish through this interface; activity code is identical in both modes.

```python
# libs/fred-core/fred_core/tasks/bus.py
class IEventBus(Protocol):
    async def publish(self, event: TaskEvent) -> None: ...
    async def subscribe(self, task_id: str) -> AsyncIterator[TaskEvent]: ...
```

| Implementation | Mechanism |
|---|---|
| `MemoryEventBus` | `asyncio.Queue` per `task_id` — no external services |
| `PostgresEventBus` | `NOTIFY task:{task_id}` on publish; `LISTEN` on subscribe |

The bus is selected alongside the scheduler backend (`memory → MemoryEventBus`, `temporal → PostgresEventBus`). The bus is for live delivery only; durability comes from `task_event_log` (§2.6).

### 2.3 `IScheduler` — narrow execution-dispatch interface

`IScheduler` is a thin interface for activity execution dispatch only (asyncio vs Temporal). It does **not** replace knowledge-flow's `BaseScheduler`, which owns ingestion-domain orchestration (workflow registration, per-user last-workflow tracking, progress computation); nor `PurgeQueueStore`, a DB-backed persistence layer. The existing `SchedulerBackend` enum and `TemporalClientProvider` in `fred-core` are its kernel.

```python
# libs/fred-core/fred_core/tasks/scheduler.py
class IScheduler(Protocol):
    async def submit(self, task_id: str, activity: Callable, params: BaseModel) -> None: ...
    async def cancel(self, task_id: str) -> None: ...
    async def get_status(self, execution_id: str) -> "ExecutionStatus | None": ...
    # None == backend could not determine status (unreachable) → caller must NOT fail the task (see §2.8)
```

| Implementation | Behaviour |
|---|---|
| `MemoryScheduler` | runs activity as an `asyncio` task; cancel via `Task.cancel()` |
| `TemporalScheduler` | submits Temporal workflow; cancel via `workflow_handle.cancel()` |

### 2.4 Activity design rules

Every activity follows these rules regardless of scheduler — this is what makes memory ↔ temporal substitution safe.

| Rule | Reason |
|---|---|
| Serializable `params` and return type (Pydantic) | Temporal serialisation; also makes memory-mode testable without mocks |
| Idempotent where possible | Temporal may retry; re-running must not duplicate rows |
| Call `ctx.heartbeat()` periodically for long steps | Temporal's liveness signal; without it the activity is presumed dead and retried |
| Progress via `ctx.emit()` only — never directly to SSE | works in both scheduler modes |

Activities run outside Temporal's replay (re-executed fresh on retry), so they may freely use `datetime.now()`, write to the DB, call external APIs — idempotency handles the retry consequence. Determinism rules apply only to the thin Temporal workflow wrapper the `TemporalScheduler` adds, not to activity functions.

```python
@dataclass
class ActivityContext:
    task_id: str
    emit:      Callable[[TaskEvent], Awaitable[None]]  # delegates to IEventBus.publish
    heartbeat: Callable[[], None]                      # no-op in memory; temporalio.activity.heartbeat() in temporal
```

### 2.5 Per-kind models and the codegen rule

All detail/event/params models live in `fred_core/tasks/models.py`; backends import them, never define their own. Current kinds: `migration`, `ingestion`, `evaluation`, `log`. `TaskLogEvent` carries only `level + message` — enough for scrollback without a second generic metadata channel.

**Adding a new `kind` is one atomic change:** (1) `*Detail` model, (2) `*TaskEvent` variant with `kind: Literal[...]`, (3) `Start*Params` + `Start*Request`, (4) extend the `TaskEvent` and `StartTaskRequest` unions, (5) `make openapi`, (6) `make codegen`. Never widen `detail` to `dict | None` or `params` to `Any`; if a frontend type is missing, strengthen the source model and regenerate.

### 2.6 Persistence — two tables (both mandatory)

One pair per database (`fred_swift` for control-plane, `knowledge_flow` for knowledge-flow), Alembic migration per backend.

`task_run` is the current-state summary (one row per task, updated in place) — answers "current status?" cheaply. `task_event_log` is the append-only journal (one row per event) — the source of truth for replay; without it `Last-Event-ID` is meaningless.

```sql
task_run (
  task_id      uuid          PRIMARY KEY,
  kind         text          NOT NULL,
  state        text          NOT NULL,        -- TaskState
  seq          integer       NOT NULL,        -- last emitted seq
  progress     float,
  step         text,
  detail       jsonb,
  error        text,
  executor     text,                          -- 'temporal' | 'memory'; NULL until submitted (§2.8)
  execution_id text,                          -- backend-native handle (Temporal workflow id); reconciliation key (§2.8)
  created_by   text,                          -- user uuid (audit)
  team_id      text,                          -- team scope; NULL for platform-level tasks (§3)
  created_at   timestamptz   NOT NULL,
  updated_at   timestamptz   NOT NULL
)

task_event_log (
  id          bigserial     PRIMARY KEY,
  task_id     uuid          NOT NULL REFERENCES task_run(task_id),
  kind        text          NOT NULL,         -- denormalised; deserialise detail jsonb on replay without a JOIN
  seq         integer       NOT NULL,
  state       text          NOT NULL,
  progress    float,  step text,  detail jsonb,  error text,
  emitted_at  timestamptz   NOT NULL,
  UNIQUE (task_id, seq)
)
```

`task_event_log.kind` is consistent with `task_run.kind`; the write path sets both in the same transaction. On reconnect the endpoint streams `task_event_log WHERE task_id = ? AND seq > ?` ordered by `seq`, then resumes the live bus; if already terminal, the final event is replayed and the connection closed.

### 2.7 HTTP endpoints

Identical contract in both backends, protected by the caller's existing auth layer. `params` is a discriminated union so each `kind` has a schema:

```python
class StartIngestionParams(BaseModel):
    resource_ids: list[str]
    profile: IngestionProcessingProfile = IngestionProcessingProfile.MEDIUM
class StartMigrationParams(BaseModel):
    operation: Literal["platform_import"]
    target_id: str | None = None
    dry_run: bool = False

class StartIngestionRequest(BaseModel): kind: Literal["ingestion"] = "ingestion"; params: StartIngestionParams
class StartMigrationRequest(BaseModel): kind: Literal["migration"] = "migration"; params: StartMigrationParams

StartTaskRequest = Annotated[Union[StartMigrationRequest, StartIngestionRequest, ...], Field(discriminator="kind")]
```

Producer-specific launch endpoints may still create tasks directly via
`task_service.start(...)`. MIGR-05 does this from
`POST /control-plane/v1/migration/import` because it uploads a bundle before
registering the migration task.

```
POST /api/v1/tasks               Body: StartTaskRequest (oneOf by kind) → 202 { task_id }
                                 Creates task_run, calls scheduler.submit, returns immediately. Never streams
                                 (so a browser reconnect can never re-trigger the operation).

GET  /api/v1/tasks               ?scope=platform|team|user (default platform), ?team_id=, ?kind=, ?state=
                                 → 200 { tasks: TaskSummary[] }  | 403 if caller lacks visibility (§3.2)
                                 TaskSummary: { task_id, kind, state, progress, step, error, target,
                                                owner, team_id, created_at, updated_at }
                                 Current state only — no history/SSE. scope=user returns created_by == caller,
                                 ordered created_at DESC, terminal states excluded unless ?state= given.

GET  /api/v1/tasks/{id}/events   → text/event-stream (each data: is a serialised TaskEvent)
                                 Replays task_event_log WHERE seq > Last-Event-ID, then live. Terminal closes.

POST /api/v1/tasks/{id}/cancel   → 202 (idempotent) | 404 not found | 409 if kind unsupported
```

The cancel endpoint is generic; a kind that doesn't support cancellation returns `409`, and consumers hide the cancel affordance for it rather than surfacing a failing button.

### 2.8 Task reconciliation — durable execution binding

A task's state advances only while its worker emits events. If the worker never runs (down at submit, crash mid-run, or a failed emit), nothing drives the task terminal and nothing reflects the executor's actual verdict — the task, and the object row it targets, stays non-terminal forever. Reconciliation closes this in `fred-core`, for every consumer.

**Execution binding.** `task_run` carries `executor` and `execution_id`. The submitter **pre-generates** the workflow id and writes the binding **before** calling `scheduler.submit(...)`, so the worker inherits it and cannot race or clobber it.

**Status capability.** `IScheduler.get_status(execution_id) -> ExecutionStatus | None` (§2.3). `ExecutionStatus` is a `fred-core` enum (`running | completed | failed | timed_out | canceled | terminated`); `TemporalScheduler` maps a `describe()`. `None` = could not determine (transient / unreachable).

**Reconcile.** For a non-terminal task with an execution binding, map the executor's status to a terminal `TaskEvent`:

| Executor status | Action |
|---|---|
| `failed` / `timed_out` / `terminated` | emit `failed` |
| `canceled` | emit `cancelled` — a user/admin cancellation is **not** a failure, so it never inflates failure counts or error history |
| `completed` but task not terminal | emit `failed` ("execution finished without completing the task") |
| `running` | leave |
| `None` (unreachable) | leave — **never false-fail on a transient outage** |

The correction is emitted as a normal `TaskEvent` via `TaskService.record(...)`, so `task_event_log`, SSE replay, and the live bus all update through the existing path — no special-case code.

**Sweeper.** A Temporal *scheduled* workflow on each task-owning worker periodically calls `reconcile_stale(grace, limit)` over `state ∈ {pending, running} ∧ execution_id IS NOT NULL ∧ updated_at < now − grace`. The SSE subscribe path may also reconcile the single task first, so a watching client sees the correction immediately.

**Principle.** Reconciliation only *reflects the executor's verdict* — it never invents fred-side timeouts or retries. Temporal owns liveness and timeouts; this layer makes the durable task mirror that truth.

---

## 3. Visibility scopes & content boundary

The `team_id` column on `task_run` drives all visibility. Scoping is enforced server-side; the frontend never filters client-side. Every activity sets `team_id` when it creates the row.

### 3.1 Scope values
| `team_id` | Meaning |
|---|---|
| `NULL` | Platform-level task (e.g. migration steps) |
| `"personal-{uid}"` | A user's personal team (e.g. document ingestion) |
| `"<team-id>"` | A regular team (e.g. delete-user, evaluation campaign) |

### 3.2 Authorization (`GET /tasks` and `GET /tasks/{id}/events`)
| Caller | `scope=platform` | `scope=team&team_id=X` | `scope=user` |
|---|---|---|---|
| Platform admin | all tasks (any `team_id`) | all tasks for team X | own tasks |
| Team admin of X | 403 | tasks where `team_id = X` | own tasks |
| Regular member of X | 403 | tasks where `team_id = X` *(read)* | own tasks |

`scope=user` is available to every authenticated caller and hard-filters `created_by = caller`. The SSE events endpoint applies the same scope rules: a team-scoped task is readable by authorized members of that team, not only its creator or a platform owner.

### 3.3 Content boundary
Task records hold only operational metadata: state, progress, step label, error, `created_by`, `team_id`, timestamps, and `target` (type/id/label). They must **never** contain document/conversation content, content-derived titles, or any `detail` field derived from ingested content. Step labels and errors are operational ("Vectorising batch 3/10", "Keycloak unreachable"), not content descriptions.

### 3.4 Dashboard surfaces
| Surface | Route | Scope | Who |
|---|---|---|---|
| Task tray (sidebar) | — | own tasks | every user |
| Team activity view | `/settings/team/activity` | `team&team_id={current}` | team admin |
| Platform task dashboard | `/admin/tasks` | `platform` | platform admin |

The tray is the real-time companion (SSE per task); the team/platform views are polling dashboards with optional drill-down to SSE.

---

## 4. Frontend contract

All types come from generated OpenAPI — never hand-written. `useTaskStream` owns one SSE connection and handles reconnect via `Last-Event-ID`.

```typescript
function useTaskStream(taskId: string | null): {
  state: TaskState | null; progress: number | null;  // null → indeterminate
  step: string | null; error: string | null;
  event: TaskEvent | null;   // narrow by event.kind to access typed detail
  events: TaskEvent[];       // full history ordered by seq
}
```

`TaskEvent` is the generated union; callers narrow with `if (event.kind === 'ingestion')` to get typed `detail`. No `Record<string, unknown>` assertions.

**Atoms/molecules:** `TaskStateBadge` (the six states), `ProgressBar` (fill 0–1; pulse when `null`), `LogLine` (info/warn/error), `BatchStepCard` (badge + bar + log + Run, disabled until prerequisite `succeeded`; cancel affordance is per-consumer).

**Task-tray re-hydration.** The Redux task slice is in-memory; on reload it is empty. A `useTaskRehydration` hook, called once from `MainLayout`, calls `GET /tasks?scope=user`, dispatches `taskRegistered({ taskId, kind, target, owner })` for each non-terminal task, and `useTaskSseManager` opens SSE per task (replaying `task_event_log` from `seq=0`). The reducer dedups on `seq > lastSeq`, so replay is always safe. `GET /tasks?scope=user` must include `target` so the tray and affected rows wire up before the first SSE event.

**Inline `TaskIndicator`.** Any object row (document, team member, …) with an active task shows it inline via the single `TaskIndicator` component — never a separate list element, never per-page duplicated logic. The selector `selectActiveTaskForTarget(type, id)` returns the first non-terminal task whose `target` matches; e.g. document rows call `selectActiveTaskForTarget("document", doc.identity.document_uid)`. While running the row adopts a processing tint; on `succeeded` the indicator disappears; on `failed`/`cancelled` it remains until the user opens `TaskDetailPopover` (acknowledgement). The popover (same component everywhere) shows target label, state, progress, step, elapsed, error, and "View all tasks".

**`target` is set at registration**, not deferred. The NDJSON upload stream co-emits `task_id` and `document_uid` on the same line (§5) so the frontend dispatches `taskRegistered` with `target: { type: "document", id: document_uid, label: file.name }`. If absent, the first SSE event's `target` is the fallback.

---

## 5. Consumers

- **Ingestion** (`kind = "ingestion"`, knowledge-flow). The `POST /upload-process-documents` NDJSON stream co-emits `task_id` and `document_uid` on the same line (the metadata row is created before the workflow is submitted), making the task linkable to its document row immediately. Ingestion panels consume `useTaskStream`; per-document live progress replaces polling.
- **Migration / platform import** (`kind = "migration"`, control-plane, platform-owner only). The task/event contract supplies durable task registration, replayable SSE, typed `MigrationDetail`, and UI rendering. The current Kea-to-Swift business order is governed by [`KEA_SWIFT_CUTOVER.md`](../ops/KEA_SWIFT_CUTOVER.md); the MIGR-05 backend workflow is governed by [`PLATFORM-IMPORT-RFC.md`](PLATFORM-IMPORT-RFC.md). Keep migration-specific step names in those documents, not in this shared task/event RFC.
- **Evaluation** (`kind = "evaluation"`, fred-evaluation). Campaign progress counters only; target `{ type: "evaluation_campaign", id, label }`; team-scoped and readable by authorized team members (§3.2). Detail per `EvaluationDetail`. See `AGENT-EVALUATION-RFC.md` (EVAL-01).
- **Lifecycle** (control-plane delete-user / purge). May emit `TaskEvent` from existing `LifecycleManagerWorkflow` activities; `PurgeQueueStore` is unchanged.

---

## 6. Impact on existing code

- **`libs/fred-core`** — add `fred_core/tasks/` (`models.py`, `bus.py`, `scheduler.py`, store/service, reconciliation); incorporate the existing `SchedulerBackend` enum and `TemporalClientProvider`.
- **`apps/knowledge-flow-backend`** — `BaseScheduler`'s public API is unchanged; its internal asyncio/Temporal dispatch delegates to `IScheduler`. `record_workflow_status` / `record_current_document` activities emit `TaskEvent`; `get_progress()` and `ProcessDocumentsProgressResponse` remain until UI callers move to `useTaskStream`. Add the SSE endpoint and `task_run` + `task_event_log` migrations; `sched_workflow_tasks` is superseded by `task_run`.
- **`apps/control-plane-backend`** — add `tasks/` wiring + `migration/` step activities (using `IScheduler` directly); `PurgeQueueStore` untouched; add migrations and the cockpit page.
- **Frozen contracts** — `RUNTIME-EXECUTION-CONTRACT.md` unchanged (task endpoints are product/admin surface). `CONTROL-PLANE-PRODUCT-CONTRACT.md` documents the `/api/v1/tasks*` endpoints and the two tables.

---

## 7. Alternatives considered

- **WebSocket instead of SSE** — rejected; communication is strictly server→client, SSE is simpler, HTTP/2 multiplexes it, and runtime streaming is already SSE.
- **Free-form `detail: dict | None`** — rejected; it weakens OpenAPI/codegen exactly where the frontend needs typed task unions.
- **Polling retained for knowledge-flow** — rejected; polling makes the client hold and diff aggregate state. SSE with `seq` is simpler for the client and cheaper under load.
- **Single monolithic migration workflow** — rejected in favour of five independent tasks for per-step retry.
