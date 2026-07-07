# RFC OPS-04 — Unified Task Event Stream & Worker-Action Audit

**ID:** OPS-04  
**Status:** confirmed (core: §1–§2, §4–§7) — 2026-06-16 · **rev. 2 (2026-07-07): worker-action audit + shared Activity surface — proposed**  
**Author:** Dimitri Tombroff  
**Date:** 2026-06-04  

> **Rev. 2 — consolidation (2026-07-07).** This revision makes OPS-04 the single home for
> two things that were about to fragment across three RFCs: the **worker-action audit log**
> and the **one shared admin Activity surface**. Every worker/admin action (ingestion,
> migration, evaluation, erasure, user deletion, …) is executed by a control-plane or
> knowledge-flow worker; each must leave a durable, admin-visible, long-lived audit record,
> and all must be viewed through *one* scoped page — not per-feature widgets scattered into
> settings. Temporal is an execution engine, **not** the audit substrate (§7).
>
> **What rev. 2 folds in (fewer RFCs, not more):**
> - **EVAL-02** (`AGENT-EVALUATION-TASK-EVENT-AMENDMENT-RFC.md`) → **retired to a tombstone.**
>   Its deliverable — a *multi-source* Activity surface aggregating knowledge-flow +
>   control-plane + evaluation producers — is the shared surface defined here (§3.4); its
>   evaluator-side wiring folds into §5.
> - **CTRLP-13 / RGPD §6** → its erasure *observability + display* half (per-row reason,
>   the shipped `erasure` kind, one shared page) is absorbed here. The RGPD RFC keeps only
>   the lifecycle *enforcement* mechanics (member-removal enqueue parity, idle sweep,
>   `last_activity_at` writer) and points here for how they surface.
>
> Rev. 2 also reconciles a real drift: the **`erasure`** kind and **`scheduled_for`** field
> shipped in CTRLP-12 but were never added to §2 — they are documented here now. The
> confirmed core (envelope, tables, endpoints, reconciliation) is unchanged; rev. 2 only
> *adds* the audit dimension (§3.3–§3.6) and the shared surface (§3.4).

---

## 1. Problem

Long-running operations exist across backends with no shared model and no real-time progress:

| Backend | Operation | Current mechanism |
|---|---|---|
| knowledge-flow | Document ingestion | Poll-based: client queries metadata to compute aggregate progress |
| control-plane | Session lifecycle purge | Fire-and-forget Temporal workflow, no client visibility |
| control-plane | kea→swift migration | Net-new |

Three structural gaps: **(1) no event stream** — progress is polled, with no live per-item feedback and no persistent run history; **(2) no shared abstraction** — knowledge-flow's `BaseScheduler` and control-plane's `PurgeQueueStore` are divergent, neither in `fred-core`, and a new consumer would add a third pattern; **(3) no unified task model** — no common `task_id`, state machine, or cross-system query/cancel.

**Rev. 2 adds a fourth gap — (4) no durable audit surface.** Even where a worker *does* run,
the record of what it did is not consistently retained, long-lived, or admin-queryable, and
some admin-triggered worker actions leave **no trace at all** (user-account deletion emits no
task; member-removal erasure enqueues a purge but no task — see CTRLP-13). Platform and team
admins have a legitimate, often regulatory, need to answer "what did the workers do to this
team's data, and when?" months later. The task model already carries almost everything an
audit record needs; the gap is *coverage* (every action emits one), *retention* (kept long,
append-only, never silently pruned), and *one surface* to read it (§3.3–§3.6).

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

class ErasureReason(str, Enum):          # why a conversation is being erased (shipped CTRLP-12)
    user_deleted   = "user_deleted"      # a user/admin deleted the conversation
    member_removed = "member_removed"    # a member was removed from the team (CTRLP-13)
    idle_expired   = "idle_expired"      # conversation idle past team max_idle (CTRLP-13)

class ErasureDetail(BaseModel):
    reason:       ErasureReason | None = None
    stores_ok:    int = 0                 # per-store fan-out progress (auditable receipt, no content)
    stores_total: int = 0
    attempts:     int = 0                 # step == "stalled" after N attempts; never auto-fails

class DeletionDetail(BaseModel):         # a principal/entity was removed (distinct from erasure of data)
    subject:           Literal["user_account"]  # extensible: "team", …
    cascade_scheduled: int = 0           # downstream erasure tasks this deletion spawned (audit chain)

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
    scheduled_for: datetime | None = None  # future due date for deferred work (erasure); None = run now

# ── per-kind variants ────────────────────────────────────────────────────────

class MigrationTaskEvent(_TaskEventBase):
    kind: Literal["migration"] = "migration";  detail: MigrationDetail | None = None
class IngestionTaskEvent(_TaskEventBase):
    kind: Literal["ingestion"] = "ingestion";  detail: IngestionDetail | None = None
class EvaluationTaskEvent(_TaskEventBase):
    kind: Literal["evaluation"] = "evaluation"; detail: EvaluationDetail | None = None
class TaskLogEvent(_TaskEventBase):
    kind: Literal["log"] = "log";              detail: TaskLogDetail
class ErasureTaskEvent(_TaskEventBase):
    kind: Literal["erasure"] = "erasure";      detail: ErasureDetail | None = None
class DeletionTaskEvent(_TaskEventBase):
    kind: Literal["deletion"] = "deletion";    detail: DeletionDetail | None = None

TaskEvent = Annotated[
    Union[MigrationTaskEvent, IngestionTaskEvent, EvaluationTaskEvent, TaskLogEvent, ErasureTaskEvent, DeletionTaskEvent],
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

All detail/event/params models live in `fred_core/tasks/models.py`; backends import them, never define their own. Current kinds: `migration`, `ingestion`, `evaluation`, `log`, **`erasure`** (shipped in CTRLP-12; documented here in rev. 2), **`deletion`** (rev. 2; principal/entity removal, e.g. user-account deletion). `TaskLogEvent` carries only `level + message` — enough for scrollback within another task's stream; it is a log-line channel, **not** a standalone operation kind, so worker actions never use `log` as their kind. `ErasureTaskEvent` carries a `reason` and per-store counts only — an auditable receipt with **no** erased content (§3.3). `deletion` vs `erasure`: **`erasure` wipes *data*** (a conversation, fanned out across stores); **`deletion` removes a *principal/entity*** (an account) and may spawn cascade erasures it links via `cascade_scheduled`.

**Adding a new `kind` is one atomic change:** (1) `*Detail` model, (2) `*TaskEvent` variant with `kind: Literal[...]`, (3) `Start*Params` + `Start*Request`, (4) extend the `TaskEvent` and `StartTaskRequest` unions, (5) `make openapi`, (6) `make codegen`. Never widen `detail` to `dict | None` or `params` to `Any`; if a frontend type is missing, strengthen the source model and regenerate.

### 2.6 Persistence — two tables (both mandatory)

**One pair, owned by control-plane** (`fred_swift`) — the single, central home for every task/audit record (rev. 2; see §2.9). The Alembic migrations for `task_run` / `task_event_log` run **only** in control-plane; no other backend creates these tables. (Rev. 1 placed a pair in each backend's database and treated the audit log as a query-time union; rev. 2 centralises — see §2.9 and §7.)

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
  scheduled_for timestamptz,                   -- future due date for deferred work (erasure); NULL = run now (§3.4)
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
                                                owner, team_id, scheduled_for, created_at, updated_at }
                                 Current state only — no history/SSE. scope=user returns created_by == caller,
                                 ordered created_at DESC, terminal states excluded unless ?state= given.
                                 Admin scopes (platform|team) return terminal tasks too — the audit view is
                                 read over the same endpoint with an explicit time window (§3.6).

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

### 2.9 Central persistence & remote recording (rev. 2)

Rev. 1 gave each backend its own tables and the audit log was a query-time union across databases (federated). Rev. 2 **centralises**: there is exactly one pair of tables, **owned by control-plane** (`fred_swift`), and every other backend records into it remotely. control-plane is the task hub — for persistence *and* for live SSE. This one journal **is** the audit log.

**The seam.** `TaskService` gets a pluggable persistence backend, exactly like `IScheduler` (memory/temporal) and `IEventBus` (memory/postgres) — the same substitution pattern, so this is idiomatic, not new machinery:

| Persistence backend | Used by | Behaviour |
|---|---|---|
| `LocalDbTaskStore` | control-plane (API + worker) | writes `task_run` / `task_event_log` directly to `fred_swift` |
| `RemoteTaskClient` | knowledge-flow API, knowledge-flow worker, evaluator | POSTs task create + events to control-plane's ingest API |

Activity code (`ctx.emit(event)`) is identical either way; only the wiring differs. Adding a producer is a config choice, not new code.

**The ingest endpoint.** control-plane exposes an internal recording API:

```
POST /control-plane/v1/tasks/ingest   Body: TaskEvent (create-or-append)  → 202
```

authenticated with a **service bearer** — the same client-credentials M2M pattern CTRLP-12 already ships, in the reverse direction (there control-plane calls knowledge-flow/runtime; here knowledge-flow/evaluator call control-plane). The endpoint requires a recognised service principal and owns `team_id`; it never trusts a caller-supplied identity for authz.

**Live SSE stays single-homed.** Because all rows live in control-plane, all task SSE is served from `/control-plane/v1/tasks/{id}/events`. A remote producer pushes an event → control-plane persists it to `task_event_log` and publishes to its `IEventBus` → connected browsers receive it. Knowledge-flow no longer serves task SSE; the ingestion UI subscribes to control-plane. This is what makes the Activity page single-source (§3.4).

**Configuration — knowledge-flow API *and* worker are configured identically.** Both are producers: the worker runs the ingestion activities that emit progress; the API creates the task. They share one config block (and the evaluator uses the same block with its own `client_id`):

```yaml
# knowledge-flow configuration — applies to the API deployment AND the worker deployment
tasks:
  persistence: remote                                  # control-plane owns the tables
  control_plane_base_url: http://control-plane:8000    # in-cluster service URL
  service_identity:                                    # client-credentials to authenticate to control-plane
    client_id: knowledge-flow
    # client_secret from env/secret; token minted lazily, audienced for control-plane
```

control-plane itself sets `tasks.persistence: local` and needs none of the remote fields.

**Startup ordering — no chicken-and-egg.** Recording a task is *lazy and failure-soft*, so nothing here creates a boot dependency:

1. **No boot-time dependency.** `RemoteTaskClient` opens no connection at startup; it authenticates and calls control-plane only when the *first task event is recorded*. Knowledge-flow (API and worker) start cleanly while control-plane is still coming up.
2. **No circular dependency.** control-plane starts without any producer; producers start without control-plane. The only shared *runtime* need is on the recording path — never the boot path. (control-plane→knowledge-flow calls, e.g. erasure fan-out, are likewise request-time, not startup.)
3. **Runtime failure degrades, never crashes.** If control-plane (or Keycloak) is unreachable when an event is pushed, the client retries with backoff; the ingestion/erasure job itself still runs to completion. Events lost during an outage are backfilled to a terminal state by the reconciliation sweeper (§2.8) — the exact mechanism that already covers "the worker emitted nothing". Live progress may stall during the outage; the durable record still converges.
4. **No deployment ordering, no init-containers.** Pods may start in any order; liveness/readiness probes are independent. Only control-plane runs the task-table migrations, so there is no cross-backend migration ordering either.
5. **Keycloak** is the one shared dependency (both backends already require it for normal auth); the service token is minted lazily on first use and cached, so even Keycloak is not a boot gate for tasks.

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

### 3.3 Content boundary — and why the audit record outlives the data

Task records hold only operational metadata: state, progress, step label, error, `created_by`, `team_id`, timestamps, and `target` (type/id/label). They must **never** contain document/conversation content, content-derived titles, or any `detail` field derived from ingested content. Step labels and errors are operational ("Vectorising batch 3/10", "Keycloak unreachable"), not content descriptions.

**This boundary is what makes an audit log RGPD-safe, and rev. 2 makes it a hard rule for the `erasure` kind.** The audit record of an erasure must **survive** the erased conversation (an admin must be able to prove, months later, that session X was erased on date Y across N stores) while containing **none** of the erased content. Two consequences:

- An `erasure` task's `target.label` is the **pseudonymous `session_id`**, never the conversation title — precisely because the record persists after the title is gone. (Producers that today set `label = title or session_id` must use `session_id` for erasure.)
- The erasure audit record (`task_run` + `task_event_log` rows) is **explicitly excluded** from the erasure fan-out: `erase_session` deletes conversation stores; it must not delete the task rows that record the erasure. This is the one place the content boundary and the retention policy (§3.6) intersect.

### 3.4 One shared Activity surface (not per-feature widgets)

**There is exactly one Activity page component.** It is rendered at two scopes, identical in every respect except the `scope`/`team_id` it queries and the authz that gates it. A feature never ships its own bespoke task list, schedule widget, or monitoring panel — erasure, ingestion, migration and evaluation are `kind` **filters** on the one page, not separate surfaces.

| Surface | Route | Query | Who | Notes |
|---|---|---|---|---|
| Task tray (sidebar) | — | `scope=user` (SSE per task) | every user | real-time companion; own in-flight tasks |
| **Activity** (team) | `/teams/{id}/activity` | `scope=team&team_id={id}` | team admin (`CAN_READ_MEMBERS`) | **first-class nav item, a peer of Members/Settings** |
| **Activity** (platform) | `/admin/activity` | `scope=platform` | platform admin (`CAN_MANAGE_PLATFORM`) | same component, platform scope |

**This corrects a shipped anti-pattern.** The erasure schedule currently renders *inside* team **Settings → Data & Retention** (`TeamSettingsRetention` embeds `ErasureSchedule`). That is wrong twice over: erasure activity is not a *setting*, and it is a feature-specific widget where a general surface belongs. Rev. 2 **removes the erasure widget from settings** and folds it into the team Activity page as the `kind=erasure` view — the exact same page and component the platform admin sees, differing only in scope. Retention *fields* (the editable `team_delete_grace` / `max_idle` inputs) stay in Settings; the *record of what was erased* moves to Activity.

**One page, faceted by kind and state.** The Activity page is a filterable table (kind, state, time window) with three natural groupings reused from the erasure work — **scheduled** (`state=pending`, ordered by `scheduled_for`), **in progress** (`running`/`cancelling`), **history** (terminal, newest first) — plus per-row drill-down to SSE. Erasure rows show their `reason` (Deleted by user / Member removed / Idle expired). The tray is the SSE companion; the Activity page is the durable dashboard (polling + optional drill-down).

**Single-source (rev. 2).** Because control-plane is the central task hub (§2.9), the tray and the Activity page read **one** endpoint — `/control-plane/v1/tasks` — regardless of which backend produced the task. Knowledge-flow ingestion, control-plane migration/erasure/deletion, and evaluator campaigns all land in the same table and stream from the same SSE endpoint, so there is no client-side aggregation across base paths. (Rev. 1 / the former EVAL-02 plan merged multiple producer mounts in the frontend; centralisation removes that complexity — the evaluator's adoption is now simply "record via the `RemoteTaskClient`", §5.)

### 3.5 Total coverage — every worker action is a task

The audit log is only trustworthy if it is **complete**. Rev. 2 adopts one invariant:

> **Every action a worker performs on a team's or user's data emits exactly one task through `fred_core.tasks`** — regardless of execution engine (Temporal, asyncio, or synchronous). No worker/admin data action bypasses the library, and no purge/erasure enqueue exists without a paired task (the CTRLP-13 invariant, generalised).

Current coverage, and the gaps rev. 2 closes:

| Worker action | Backend | Emits a task today? | Target |
|---|---|---|---|
| Document ingestion | knowledge-flow | ✅ `ingestion` | keep |
| Platform import / migration | control-plane | ✅ `migration` | keep |
| Evaluation campaign | evaluator | ⚠️ bespoke SSE | → `evaluation` task (EVAL-02, §5) |
| Conversation deferred delete | control-plane | ✅ `erasure` (`user_deleted`) | keep |
| **Member removal → conversation erasure** | control-plane | ❌ purge row, no task | → `erasure` (`member_removed`) — **CTRLP-13** |
| **Idle-expiry erasure** | control-plane | ❌ no sweep at all | → `erasure` (`idle_expired`) — **CTRLP-13** |
| **User-account deletion** | control-plane | ❌ Keycloak-only, no task | → emit a **`deletion`** task (`subject=user_account`) |

The lifecycle-*enforcement* half of the erasure gaps (wiring the enqueue, the idle sweep, the `last_activity_at` writer) stays in CTRLP-13 / the RGPD RFC; this RFC owns the requirement that each such action *surfaces as a task*. User-account-deletion coverage is new scope introduced here (small: one emit at the deletion site).

### 3.6 Audit retention & immutability

An audit log is worthless if it is short-lived or editable. Rev. 2 sets three rules on the single, central journal (§2.9) — no new store, one home, so retention/immutability/export are configured once rather than N times:

- **Append-only.** `task_event_log` is already insert-only (§2.6); rev. 2 makes it contractual: events are never updated or deleted in place. `task_run` remains the mutable current-state summary; the journal is the immutable truth.
- **Long retention, no silent pruning.** Terminal tasks are a UI *filter* (`scope=user` hides them), never a deletion. Admin scopes return terminal history within an explicit time window (§2.7). There is **no cleanup job** that drops task history; if archival is ever needed it is an explicit, configured, audited policy — not an implicit TTL. (Temporal's own history TTL is irrelevant — it is not the audit store, §7.)
- **Erasure records are exempt from erasure.** As stated in §3.3, `erase_session` must not delete the `task_run`/`task_event_log` rows that record it. The proof-of-erasure outlives the data it erased, carrying only pseudonymous ids and per-store counts.

Together these turn the task journal into a genuine, regulator-facing audit trail: complete (§3.5), scoped (§3.2), content-safe (§3.3), and durable (§3.6) — read through one page (§3.4).

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

- **Ingestion** (`kind = "ingestion"`, knowledge-flow). The `POST /upload-process-documents` NDJSON stream co-emits `task_id` and `document_uid` on the same line (the metadata row is created before the workflow is submitted), making the task linkable to its document row immediately. Ingestion panels consume `useTaskStream`; per-document live progress replaces polling. **Rev. 2:** knowledge-flow (API *and* worker) records through `RemoteTaskClient` to control-plane (§2.9); it no longer owns task tables or serves task SSE — the frontend subscribes to control-plane for ingestion progress.
- **Migration / platform import** (`kind = "migration"`, control-plane, platform-owner only). The task/event contract supplies durable task registration, replayable SSE, typed `MigrationDetail`, and UI rendering. The current Kea-to-Swift business order is governed by [`KEA_SWIFT_CUTOVER.md`](../ops/KEA_SWIFT_CUTOVER.md); the MIGR-05 backend workflow is governed by [`PLATFORM-IMPORT-RFC.md`](PLATFORM-IMPORT-RFC.md). Keep migration-specific step names in those documents, not in this shared task/event RFC.
- **Evaluation** (`kind = "evaluation"`, standalone `fred-agent-evaluator`). Campaign progress counters only; target `{ type: "evaluation_campaign", id, label }`; team-scoped and readable by authorized team members (§3.2). Detail per `EvaluationDetail`. **Adoption (folded from EVAL-02):** the evaluator records through `RemoteTaskClient` to control-plane (§2.9) and drops its bespoke `/campaigns/{id}/events` SSE — it does *not* mount its own `/tasks` surface; the frontend reads control-plane (§3.4 single-source). Task `succeeded` ≠ evaluation verdict — the task plane stays distinct from the evaluation-domain plane. See `AGENT-EVALUATION-RFC.md` (EVAL-01) §5.
- **Erasure** (`kind = "erasure"`, control-plane; shipped CTRLP-12). Deferred conversation delete emits a future-dated `erasure` task (`scheduled_for = due_at`), advanced `pending → running → succeeded` by the lifecycle worker; a partial receipt stays `running` for retry, never `failed`. `ErasureDetail` carries `reason` + per-store counts, no content (§3.3). **CTRLP-13** extends the producer so member-removal and idle-expiry enqueues each emit a paired task (§3.5); the enforcement mechanics live in the RGPD RFC, the surfacing here.
- **Deletion** (`kind = "deletion"`, control-plane; rev. 2). A principal/entity is removed — user-account deletion today (`DeletionDetail.subject = "user_account"`), extensible to team disband later. The task is emitted at the action site (`delete_user`) and may be immediately terminal for a synchronous op; `cascade_scheduled` counts the downstream `erasure` tasks the deletion spawns, giving an auditable "account deleted → N conversations erased" chain. This closes the last coverage gap in §3.5. `PurgeQueueStore` and `LifecycleManagerWorkflow` are unchanged; they gain a task emission, not a rewrite.

---

## 6. Impact on existing code

- **`libs/fred-core`** — add `fred_core/tasks/` (`models.py`, `bus.py`, `scheduler.py`, store/service, reconciliation); incorporate the existing `SchedulerBackend` enum and `TemporalClientProvider`.
- **`apps/knowledge-flow-backend`** — `BaseScheduler`'s public API is unchanged; its internal asyncio/Temporal dispatch delegates to `IScheduler`. `record_workflow_status` / `record_current_document` activities emit `TaskEvent`; `get_progress()` and `ProcessDocumentsProgressResponse` remain until UI callers move to `useTaskStream`. **Rev. 2:** knowledge-flow (API + worker) records via `RemoteTaskClient` (§2.9) — it **no longer owns `task_run`/`task_event_log` tables or a task SSE endpoint** (rev. 1 added them here; rev. 2 removes that ownership). Configure `tasks.persistence: remote` + `control_plane_base_url` + a client-credentials `service_identity` on both the API and worker deployments.
- **`apps/control-plane-backend`** — add `tasks/` wiring + `migration/` step activities (using `IScheduler` directly); `PurgeQueueStore` untouched; own the central `task_run` + `task_event_log` migrations and the `POST /tasks/ingest` endpoint (§2.9); serve all task SSE; host the Activity page. Configure `tasks.persistence: local`.
- **Frozen contracts** — `RUNTIME-EXECUTION-CONTRACT.md` unchanged (task endpoints are product/admin surface). `CONTROL-PLANE-PRODUCT-CONTRACT.md` documents the `/api/v1/tasks*` endpoints (incl. `POST /tasks/ingest`), the `erasure`/`deletion` kinds, and the two central tables.

---

## 7. Alternatives considered

- **WebSocket instead of SSE** — rejected; communication is strictly server→client, SSE is simpler, HTTP/2 multiplexes it, and runtime streaming is already SSE.
- **Free-form `detail: dict | None`** — rejected; it weakens OpenAPI/codegen exactly where the frontend needs typed task unions.
- **Polling retained for knowledge-flow** — rejected; polling makes the client hold and diff aggregate state. SSE with `seq` is simpler for the client and cheaper under load.
- **Single monolithic migration workflow** — rejected in favour of five independent tasks for per-step retry.
- **Temporal workflow history as the audit log** — rejected. Temporal history is retention-capped, keyed by workflow-id not by team/user, has no team-scoped authz, and does not cover non-Temporal actions (synchronous user deletion, asyncio ingestion). Temporal is one execution engine behind `IScheduler`; the durable, queryable, content-safe audit substrate is `task_event_log` (§3.6).
- **A separate dedicated audit-log store/service** — rejected. `task_run` + append-only `task_event_log` already carry state, target, actor (`created_by`), scope (`team_id`), timing, and a per-store receipt, behind one scoped API and one page. A parallel audit store would duplicate all of it and re-open the coverage problem. Audit is a *policy* on the existing journal (§3.6), not new infrastructure.
- **A per-feature schedule/monitor widget (e.g. erasure schedule in team settings)** — rejected, and actively reversed in rev. 2. Feature-specific surfaces fragment the operator's view and each re-implement scoping/empty-states. One Activity page faceted by `kind` (§3.4) is the invariant.
- **Federated per-backend task tables** (rev. 1) — rejected in rev. 2. A pair of tables in every backend's DB makes "the audit log" a query-time union across databases, with retention/immutability/export enforced N times and cross-backend queries fanning out. Rev. 2 centralises the tables in control-plane and has producers record remotely (§2.9); this also collapses the frontend to single-source (§3.4). Cost — producers depend on control-plane on the *recording* path — is bounded: recording is lazy and failure-soft, and outages are covered by the existing reconciliation sweeper (§2.8), so there is no startup coupling.
