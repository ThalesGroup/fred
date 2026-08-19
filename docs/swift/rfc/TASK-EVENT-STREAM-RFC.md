# RFC OPS-04 — Unified Task Event Stream & Worker-Action Audit

**ID:** OPS-04  
**Status:** confirmed (core: §1–§2, §4–§7) — 2026-06-16 · rev. 2 (2026-07-07): worker-action audit + shared Activity surface — proposed · rev. 3 (2026-07-25): persisted acknowledgement — proposed, driven by OBSERV-02's role-based dashboard finalization (§2.10) · **rev. 4 (2026-07-27): per-service task persistence, rejects rev. 2's central-ownership/`RemoteTaskClient` design (§2.6/§2.9) — confirmed** · **rev. 5 (2026-08-14): per-service task persistence SHIPPED as prefixed tables in the shared database, not a dedicated one (#2170) — settled, see [`CONTROL-PLANE-PRODUCT-CONTRACT.md` § Persistence](../design/CONTROL-PLANE-PRODUCT-CONTRACT.md)**  
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
> - **EVAL-02** → **folded in here.**
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
>
> **Amendment (2026-07-14, AUTHZ-07 Step 3).** Two additive,
> backward-compatible contract changes, both documented in §2.1/§2.7 below: (1) `MigrationDetail`
> gained an optional `result: MigrationResult | None` field — populated only on the terminal
> `succeeded` event, `None` on every intermediate progress event exactly as before — so a
> partial reconciliation (non-empty `result.warnings`) is distinguishable from full success
> without a new `TaskState`; (2) `TaskSummary` (the `GET /tasks` response shape) gained an
> optional `detail` field, typed per `kind` the same way `TaskEvent.detail` already is, so the
> last-persisted detail (already retained by `record_event`'s "keep the last non-null detail"
> rule, §2.6) survives a reload instead of being dropped at the list-endpoint boundary. Neither
> change adds a table, an endpoint, or a parallel model — see
> `CONTROL-PLANE-PRODUCT-CONTRACT.md §27` for
> the full rationale and the producer-side wiring (`import_export/api.py`).

> **Amendment (2026-08-14) — rev. 5, shipped: prefixed tables, not a dedicated database (#2170).**
> Rev. 4's diagnosis below is confirmed and unchanged — two backends, one shared `task_run`, no
> per-backend scoping, duplicate rows on the Activity page. Its **remedy** is superseded: isolating
> knowledge-flow needed no second database, no `POSTGRES_KNOWLEDGE_FLOW_DB`, and no second engine in
> `ApplicationContext`. Each backend now declares its own prefixed pair (`cp_task_run`/
> `cp_task_event_log`, `kf_task_run`/`kf_task_event_log`) on its **own** declarative `Base`, from
> shared column mixins in `fred_core.tasks.orm_models`; fred-core maps nothing itself.
>
> Prefixes beat a dedicated database on the axis rev. 4 could not address: issue #2314 shows the
> Alembic ownership filter is inert because `_owned_tables` is derived from the shared `CoreBase`,
> and notes that "a dedicated knowledge-flow database would sidestep cross-service collision, but
> would not fix autogenerate proposing foreign tables within a tree." Moving these two tables onto
> per-backend `Base`es does fix it for them — each pair is now in exactly one tree's metadata.
>
> **This decision is settled and shipped, so it does not live here.** §2.6 and §2.9 below are
> trimmed to pointers per CLAUDE.md's RFC-vs-doc rule; the durable what/why is in
> [`CONTROL-PLANE-PRODUCT-CONTRACT.md` § Persistence](../design/CONTROL-PLANE-PRODUCT-CONTRACT.md).
> Out of scope and still open: #2314 (ownership filter, incl. removing knowledge-flow's startup
> `CoreBase.metadata.create_all` — #2313, closed as consolidated into it).

> **Amendment (2026-07-27) — rev. 4, per-service task persistence, rejects central ownership.**
> Rev. 2's §2.6/§2.9 (one `task_run`/`task_event_log` pair owned by control-plane, every other
> backend recording remotely via a `RemoteTaskClient`) was never confirmed — it shipped as
> "proposed" and was never implemented: `RemoteTaskClient` does not exist anywhere in the
> codebase, and knowledge-flow's own Alembic chain (`1c9a54674ebf_add_task_run_scheduled_for.py`
> and siblings) still `ALTER`s `task_run` in place, never `CREATE`s it — it silently rides on
> control-plane's copy of the table.
>
> This was found, not theorised: control-plane-backend and knowledge-flow-backend are wired to
> the **same physical Postgres database** (`POSTGRES_FRED_DB`, both `docker-compose-postgres.yml`
> and the GKE Helm secrets), and `TaskRunRow`/`TaskEventLogRow` (`fred_core/tasks/orm_models.py`)
> carry no per-service discriminator — so every task either backend creates lands in one shared
> table, and the admin Activity page (§3.4), which queries each backend's `GET /tasks`
> independently and merges client-side, displayed every task **twice**.
>
> **Decision: reject centralisation, adopt per-service isolation instead.** Each backend keeps
> writing its own `task_run`/`task_event_log` **locally** (no new HTTP recording path, no new
> service-to-service M2M auth surface, no new single point of failure for every other backend's
> task visibility) — the same model already proven correct by the `evaluation` backend, which has
> carried its own dedicated Postgres database since 2026-07-07 and has never shown a duplicate.
> The fix is infrastructure-only: give knowledge-flow the same dedicated database evaluation
> already has, scoped **only** to `task_run`/`task_event_log` — knowledge-flow's `tag`/
> `document_metadata` tables stay in the shared database, because control-plane's platform
> import/export/reset (`CONTROL-PLANE-PRODUCT-CONTRACT.md` §27/§31)
> genuinely needs them in the same atomic transaction as its own `agent_instance`/`team_metadata`/
> `prompt` rows — task rows never participate in that transaction, so nothing requires them to be
> co-located. See §2.9 (rewritten), §2.6, §3.4, §5, §6 and §7 below for the corrected design; the
> superseded rev. 2 text is kept, marked, not deleted. Execution tracked as a `swift ga`
> GitHub issue (per-service Postgres isolation for knowledge-flow's task tables).

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

class MigrationResult(BaseModel):    # terminal-only structured outcome (AUTHZ-07 Step 3)
    import_id: str; source_platform: str
    identities_created: int; users_processed: int; users_skipped: list[str]
    teams_imported: int; teams_skipped: int; teams_provisioned: int
    team_roles_granted: int; team_roles_skipped: int; platform_roles_granted: int
    agents_imported: int; agents_skipped: int; agents_gap: int
    tags_imported: int; tags_skipped: int
    docs_imported: int; docs_skipped: int
    warnings: list[str]

class MigrationDetail(BaseModel):
    step_id: str; processed: int; total: int; failed: int
    result: MigrationResult | None = None   # populated only on the terminal `succeeded` event

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

**One pair per backend, prefixed by its owner** (rev. 5, shipped #2170; corrects both rev. 2's
"one pair, owned by control-plane" — proposed, never built — and rev. 4's "each in its own
database" — confirmed, never built). control-plane owns `cp_task_run`/`cp_task_event_log` and
knowledge-flow owns `kf_task_run`/`kf_task_event_log`, both migrated by their own Alembic tree
against the shared `fred` database; `evaluation` keeps the unprefixed pair in the separate
database it already has. Table list and rationale:
[`CONTROL-PLANE-PRODUCT-CONTRACT.md` § Persistence](../design/CONTROL-PLANE-PRODUCT-CONTRACT.md). ~~Rev. 2 text (superseded, kept for history): "owned by control-plane (`fred_swift`) — the
single, central home for every task/audit record. The Alembic migrations for `task_run` /
`task_event_log` run only in control-plane; no other backend creates these tables."~~ (Rev. 1
placed a pair in each backend's database and treated the audit log as a query-time union — the
right instinct, wrong reason rejected in rev. 2's write-up: rev. 1 wasn't wrong about *where* the
tables live, only that nothing scoped `GET /tasks` to the calling backend's own rows when two
backends shared a database. Rev. 4 keeps rev. 1's per-backend tables and fixes the real bug —
see §2.9.)

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
                                                owner, team_id, scheduled_for, created_at, updated_at,
                                                detail }  # detail: last-persisted per-kind detail
                                                          # (typed per `kind`, e.g. MigrationDetail),
                                                          # None for kinds with no summary detail model
                                                          # or a task recorded before this field existed
                                                          # (AUTHZ-07 Step 3)
                                 Current state only — no history/SSE. scope=user returns created_by == caller,
                                 ordered created_at DESC, terminal states excluded unless ?state= given.
                                 Admin scopes (platform|team) return terminal tasks too — the audit view is
                                 read over the same endpoint with an explicit time window (§3.6).

GET  /api/v1/tasks/{id}/events   → text/event-stream (each data: is a serialised TaskEvent)
                                 Replays task_event_log WHERE seq > Last-Event-ID, then live. Terminal closes.

POST /api/v1/tasks/{id}/cancel   → 202 (idempotent) | 404 not found | 409 if kind unsupported

POST /api/v1/tasks/{id}/ack      → 200 { task_id, acknowledged_at, acknowledged_by }  (rev. 3, §2.10)
                                 404 not found | 409 if the task does not need attention
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

### 2.9 Per-service task persistence (rev. 5, 2026-08-14 — shipped; replaces rev. 2's centralisation below)

**Each backend persists its own task pair, in its own prefixed tables, and serves its own
`GET /tasks`/SSE.** Shipped in #2170. The schema, the naming rule and the reasoning are in
[`CONTROL-PLANE-PRODUCT-CONTRACT.md` § Persistence](../design/CONTROL-PLANE-PRODUCT-CONTRACT.md)
— not restated here. Rev. 4's dedicated-database remedy (`POSTGRES_KNOWLEDGE_FLOW_DB`, a second
engine in `ApplicationContext`) was **not** built; see the rev. 5 amendment at the top for why.

**The Activity page stays multi-source, by design, not as a stopgap** (corrects §3.4's "Rev. 2:
single-source" text below): the frontend already queries each backend's own `GET /tasks`
independently and merges client-side (`TaskActivity.tsx`) — that code was written *assuming*
per-backend isolation, and needs no change once the isolation is real. `taskBackendFor` in
`taskKinds.ts` is already the source of truth for which backend a given `kind` belongs to.

**Rejected alternative — central persistence + `RemoteTaskClient` (rev. 2, proposed 2026-07-07,
never implemented, formally rejected 2026-07-27).** Kept below for history; do not build this.

> Rev. 2 proposed centralising: exactly one pair of tables, owned by control-plane, with every
> other backend recording into it remotely over HTTP (a `RemoteTaskClient` POSTing to a new
> `POST /control-plane/v1/tasks/ingest`, authenticated with a client-credentials service bearer),
> so that control-plane became the task hub for both persistence and live SSE.
>
> **Why this is rejected, not merely "not started":** (1) it puts a synchronous HTTP round-trip
> and a new M2M auth dependency on the *recording path* of an unrelated backend's hot loop — a
> single large ingestion job can emit hundreds of progress events; (2) it makes control-plane a
> single point of failure for every other backend's task visibility, not just its own; (3) it
> hands control-plane ownership of data that is knowledge-flow's own operational concern (its
> ingestion pipeline's progress), which is a domain-boundary violation, not a simplification;
> (4) it requires a new authenticated ingest endpoint, a new service-identity/client-credentials
> wiring on two more deployments (knowledge-flow API + worker), and removes knowledge-flow's
> ability to report its own task status if control-plane is degraded — real new failure modes for
> a problem (accidental table sharing) that infrastructure isolation fixes with zero new code.
>
> The startup-ordering argument made for it below (lazy, failure-soft recording) is real, but it
> only justifies *tolerating* the coupling `RemoteTaskClient` introduces — it was never a reason
> to introduce that coupling in the first place when per-service isolation avoids it entirely.
>
> ~~**The seam.** `TaskService` gets a pluggable persistence backend, exactly like `IScheduler`
> (memory/temporal) and `IEventBus` (memory/postgres) — the same substitution pattern, so this is
> idiomatic, not new machinery: `LocalDbTaskStore` (control-plane, writes directly) vs
> `RemoteTaskClient` (knowledge-flow API/worker, evaluator — POSTs to control-plane's ingest API).
> Activity code (`ctx.emit(event)`) is identical either way; only the wiring differs.~~ This seam
> was never built — `TaskStore` has no pluggable-backend abstraction today, despite the RFC text
> above describing it as already-idiomatic-like-`IScheduler`.
>
> ~~**Configuration** — knowledge-flow API and worker would share one config block
> (`tasks.persistence: remote`, `control_plane_base_url`, a `service_identity` client-credentials
> block); control-plane would set `tasks.persistence: local`.~~
>
> ~~**Startup ordering** — recording would be lazy and failure-soft: no boot-time dependency (the
> client only connects on the first recorded event), no circular dependency, runtime failures
> degrade via retry-with-backoff and the existing reconciliation sweeper (§2.8) rather than
> crashing, and only control-plane would run the task-table migrations so there'd be no
> cross-backend migration ordering.~~

### 2.10 Persisted acknowledgement (rev. 3, 2026-07-25)

**Gap.** §4 describes opening `TaskDetailPopover` on a `failed`/`cancelled` task as
"acknowledgement." As-implemented this is aspirational, not wired: the popover and
`TaskIndicator` dispatch nothing, and the only acknowledgement action that exists
(`failuresAcknowledged`, fired when the task *tray* opens) is a client-only Redux
flag that resets on reload and is never shared between viewers. OBSERV-02's
role-based dashboards give `platform_admin`/`team_admin`/`team_editor` an
"Activités" panel — reusing `TaskActivity` (§3.4) as-is — whose central use case
*is* dismissing a handled failure (a recurring ingestion error, a stalled erasure).
That needs one admin's dismissal to be visible to every other admin looking at the
same scope, which requires a real server-side state, not a per-browser flag.

**Needs-attention predicate.** Not every terminal task is acknowledgeable —
`succeeded` tasks are already self-explanatory history (§3.4's "completed" group).
A task needs attention, and therefore exposes an acknowledge affordance, when:
`state IN (failed, cancelled)` OR (`kind = erasure AND step = "stalled"`, §2 —
erasure deliberately never reaches `failed`, so its attention signal is the
`step` convention already in place). This predicate is computed, not stored.

**Persistence.** Two nullable columns added to `task_run` (not a new table — a
task's acknowledgement is a fact about that task, and it must never survive
independently of the row it qualifies): `acknowledged_at: timestamptz | None`,
`acknowledged_by: str | None` (uid). Both `NULL` = not acknowledged (the default
and the only state for every task recorded before this migration). Acknowledging
a currently-non-terminal task is a no-op reserved for later — the column only
ever gets set once the needs-attention predicate is already true.

**Endpoint** (added to §2.7's table):

```
POST /api/v1/tasks/{id}/ack     → 200 { task_id, acknowledged_at, acknowledged_by }
                                   404 not found | 409 if the needs-attention predicate is false
                                   (nothing to acknowledge — mirrors the existing /cancel 409 pattern)
```

No `DELETE`/unacknowledge in v1 — an admin who acknowledged in error re-opens the
same underlying problem by acting on it directly (re-running ingestion, etc.),
which is out-of-band from this endpoint; a task that fails *again* is a new event
sequence past the ack timestamp, so the needs-attention predicate can re-trigger
naturally without needing an unacknowledge affordance — **provided the panel
reads live `state`, not a cached "was once acked" bit**: an acknowledged row with
`state=failed` from a later, distinct failure is still "needs attention" because
its *current* terminal event's `seq`/`timestamp` is newer than `acknowledged_at`.
The panel query is therefore: needs-attention AND (`acknowledged_at IS NULL` OR
`acknowledged_at < ` the task's last-event timestamp) — never a bare
`acknowledged_at IS NULL` check, or a second failure on the same task id would
stay silently hidden.

**Authorization.** Reuses `authorize_task_access` unchanged (§3.2) — whoever can
view a task (creator, platform admin, or a `CAN_READ_MEMBERS` reader of its team)
can acknowledge it. No new permission, no new check.

**Frontend.** `TaskDetailPopover` gains an "Acknowledge" action, shown only when
the needs-attention predicate holds and `acknowledged_at` is unset; `TaskCard`
(the tray/list row) shows a muted state once acknowledged rather than disappearing
outright, so the dismissal is visible, not silent. This replaces
`failuresAcknowledged`/the tray-bulk-open gesture as the acknowledgement path —
that Redux action and its dispatch site are removed once the persisted path
lands, rather than kept as a second, inconsistent mechanism.

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

**Multi-source, per backend (rev. 4 — corrects the "single-source" text this replaces).** The tray
and the Activity page query each backend's own `GET /tasks` independently and merge client-side
(`TaskActivity.tsx`, `taskBackendFor` in `taskKinds.ts` routing each `kind` to its owning backend)
— this is already implemented and is the permanent design, not a rev.-1 leftover to remove. See
§2.9 for why: each backend persists its own tasks in its own database, so there is nothing to
centralise. ~~Rev. 2 text (superseded): "Because control-plane is the central task hub (§2.9), the
tray and the Activity page read one endpoint — `/control-plane/v1/tasks` — regardless of which
backend produced the task... there is no client-side aggregation across base paths."~~

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

An audit log is worthless if it is short-lived or editable. Rev. 2 sets three rules; rev. 4 (§2.9)
applies them **per backend's own journal** rather than one central one — each backend configures
retention/immutability/export for its own `task_event_log` (there are as many journals as
backends, not one), which is a small repeat, not the N-fold burden rev. 2 worried about, since
there are only three backends and the rules themselves (append-only, no pruning, erasure-exempt)
are identical library defaults in `fred_core.tasks`, not something each backend hand-implements:

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

**Inline `TaskIndicator`.** Any object row (document, team member, …) with an active task shows it inline via the single `TaskIndicator` component — never a separate list element, never per-page duplicated logic. The selector `selectActiveTaskForTarget(type, id)` returns the first non-terminal task whose `target` matches; e.g. document rows call `selectActiveTaskForTarget("document", doc.identity.document_uid)`. While running the row adopts a processing tint; on `succeeded` the indicator disappears; on `failed`/`cancelled` it remains until acknowledged (§2.10) — the user opens `TaskDetailPopover` and acts on its "Acknowledge" affordance, which calls `POST /tasks/{id}/ack` and is then visible to every viewer of that task's scope, not just the one browser. The popover (same component everywhere) shows target label, state, progress, step, elapsed, error, and "View all tasks".

**`target` is set at registration**, not deferred. The NDJSON upload stream co-emits `task_id` and `document_uid` on the same line (§5) so the frontend dispatches `taskRegistered` with `target: { type: "document", id: document_uid, label: file.name }`. If absent, the first SSE event's `target` is the fallback.

---

## 5. Consumers

- **Ingestion** (`kind = "ingestion"`, knowledge-flow). The `POST /upload-process-documents` NDJSON stream co-emits `task_id` and `document_uid` on the same line (the metadata row is created before the workflow is submitted), making the task linkable to its document row immediately. Ingestion panels consume `useTaskStream`; per-document live progress replaces polling. **Rev. 5 (shipped #2170; corrects rev. 4 and rev. 2 below):** knowledge-flow (API and worker) keeps owning its task tables and its own task SSE, as `kf_task_run`/`kf_task_event_log` in the shared `fred` database (§2.9) — not the dedicated database rev. 4 called for. The frontend's ingestion panels subscribe to knowledge-flow directly, same as today. ~~Rev. 2 text (superseded, never built): "knowledge-flow (API and worker) records through `RemoteTaskClient` to control-plane; it no longer owns task tables or serves task SSE — the frontend subscribes to control-plane for ingestion progress."~~
- **Migration / platform import** (`kind = "migration"`, control-plane, platform-owner only). The task/event contract supplies durable task registration, replayable SSE, typed `MigrationDetail`, and UI rendering. The current Kea-to-Swift business order is governed by [`KEA_SWIFT_CUTOVER.md`](../ops/KEA_SWIFT_CUTOVER.md); the MIGR-05 backend workflow is governed by `CONTROL-PLANE-PRODUCT-CONTRACT.md §27`. Keep migration-specific step names in those documents, not in this shared task/event RFC.
- **Evaluation** (`kind = "evaluation"`, standalone `fred-agent-evaluator`). Campaign progress counters only; target `{ type: "evaluation_campaign", id, label }`; team-scoped and readable by authorized team members (§3.2). Detail per `EvaluationDetail`. **Adoption (folded from EVAL-02; rev. 4 corrects the text below):** the evaluator owns its own `task_run`/`task_event_log` in its own already-dedicated database (provisioned 2026-07-07, `fred-deployment-factory` commit `86f2c3b`) and serves its own `/tasks` — the frontend queries it directly (`useListTasksEvaluationV1TasksGetQuery`, §2.9), exactly the pattern rev. 4 extends to knowledge-flow. This is, and was always, correct — the evaluator never needed `RemoteTaskClient` to avoid duplication, because it never shared a database with anyone. Task `succeeded` ≠ evaluation verdict — the task plane stays distinct from the evaluation-domain plane. See `AGENT-EVALUATION-RFC.md` (EVAL-01) §5. ~~Rev. 2 text (superseded, never built): "the evaluator records through `RemoteTaskClient` to control-plane and drops its bespoke `/campaigns/{id}/events` SSE — it does not mount its own `/tasks` surface; the frontend reads control-plane (single-source)."~~
- **Erasure** (`kind = "erasure"`, control-plane; shipped CTRLP-12). Deferred conversation delete emits a future-dated `erasure` task (`scheduled_for = due_at`), advanced `pending → running → succeeded` by the lifecycle worker; a partial receipt stays `running` for retry, never `failed`. `ErasureDetail` carries `reason` + per-store counts, no content (§3.3). **CTRLP-13** extends the producer so member-removal and idle-expiry enqueues each emit a paired task (§3.5); the enforcement mechanics live in the RGPD RFC, the surfacing here.
- **Deletion** (`kind = "deletion"`, control-plane; rev. 2). A principal/entity is removed — user-account deletion today (`DeletionDetail.subject = "user_account"`), extensible to team disband later. The task is emitted at the action site (`delete_user`) and may be immediately terminal for a synchronous op; `cascade_scheduled` counts the downstream `erasure` tasks the deletion spawns, giving an auditable "account deleted → N conversations erased" chain. This closes the last coverage gap in §3.5. `PurgeQueueStore` and `LifecycleManagerWorkflow` are unchanged; they gain a task emission, not a rewrite.

---

## 6. Impact on existing code

- **`libs/fred-core`** — add `fred_core/tasks/` (`models.py`, `bus.py`, `scheduler.py`, store/service, reconciliation); incorporate the existing `SchedulerBackend` enum and `TemporalClientProvider`.
- **`apps/knowledge-flow-backend`** — `BaseScheduler`'s public API is unchanged; its internal asyncio/Temporal dispatch delegates to `IScheduler`. `record_workflow_status` / `record_current_document` activities emit `TaskEvent`; `get_progress()` and `ProcessDocumentsProgressResponse` remain until UI callers move to `useTaskStream`. **Rev. 5 (shipped #2170; corrects rev. 4 and rev. 2 below):** knowledge-flow keeps owning its task tables and its task SSE endpoint (§2.9) — the only change is that they are renamed `kf_task_run`/`kf_task_event_log` and declared on knowledge-flow's own `Base`, so they stop colliding with control-plane's copy in the shared `fred` database. `ApplicationContext` gains **no** second engine and no new database: rev. 4's `POSTGRES_KNOWLEDGE_FLOW_DB` remedy was confirmed but never built. `metadata_store`/`tag_store`/`resource_store` are unaffected. ~~Rev. 2 text (superseded, never built): "knowledge-flow (API + worker) records via `RemoteTaskClient` — it no longer owns `task_run`/`task_event_log` tables or a task SSE endpoint. Configure `tasks.persistence: remote` + `control_plane_base_url` + a client-credentials `service_identity` on both the API and worker deployments."~~
- **`apps/control-plane-backend`** — add `tasks/` wiring + `migration/` step activities (using `IScheduler` directly); `PurgeQueueStore` untouched; own its own `task_run` + `task_event_log` migrations (in the `fred` database it already has); serve its own task SSE; host the Activity page. ~~Rev. 2 text (superseded): "own the central `task_run` + `task_event_log` migrations and the `POST /tasks/ingest` endpoint; serve all task SSE."~~ There is no `POST /tasks/ingest` endpoint under rev. 4 — nothing records remotely.
- **Frozen contracts** — `RUNTIME-EXECUTION-CONTRACT.md` unchanged (task endpoints are product/admin surface). `CONTROL-PLANE-PRODUCT-CONTRACT.md` documents control-plane's own `/api/v1/tasks*` endpoints and the `erasure`/`deletion` kinds — no `POST /tasks/ingest`, no cross-backend table (rev. 4).

---

## 7. Alternatives considered

- **WebSocket instead of SSE** — rejected; communication is strictly server→client, SSE is simpler, HTTP/2 multiplexes it, and runtime streaming is already SSE.
- **Free-form `detail: dict | None`** — rejected; it weakens OpenAPI/codegen exactly where the frontend needs typed task unions.
- **Polling retained for knowledge-flow** — rejected; polling makes the client hold and diff aggregate state. SSE with `seq` is simpler for the client and cheaper under load.
- **Single monolithic migration workflow** — rejected in favour of five independent tasks for per-step retry.
- **Temporal workflow history as the audit log** — rejected. Temporal history is retention-capped, keyed by workflow-id not by team/user, has no team-scoped authz, and does not cover non-Temporal actions (synchronous user deletion, asyncio ingestion). Temporal is one execution engine behind `IScheduler`; the durable, queryable, content-safe audit substrate is `task_event_log` (§3.6).
- **A separate dedicated audit-log store/service** — rejected. `task_run` + append-only `task_event_log` already carry state, target, actor (`created_by`), scope (`team_id`), timing, and a per-store receipt, behind one scoped API and one page. A parallel audit store would duplicate all of it and re-open the coverage problem. Audit is a *policy* on the existing journal (§3.6), not new infrastructure.
- **A per-feature schedule/monitor widget (e.g. erasure schedule in team settings)** — rejected, and actively reversed in rev. 2. Feature-specific surfaces fragment the operator's view and each re-implement scoping/empty-states. One Activity page faceted by `kind` (§3.4) is the invariant.
- **Federated per-backend task tables** (rev. 1) — rev. 2 rejected this in favour of centralisation; **rev. 4 reverses that call and re-adopts it** (§2.9). Rev. 2's stated cost ("the audit log becomes a query-time union across databases, retention/immutability/export enforced N times") turned out smaller in practice than the cost of the alternative: there are exactly three backends, the retention/immutability rules are identical `fred_core.tasks` library defaults rather than hand-implemented per backend (§3.6), and "cross-backend queries fanning out" describes exactly one query — the Activity page, which already does this today and needs no new code. Rev. 1's actual flaw was never "federated tables" — it was that nothing scoped a backend's `GET /tasks` to rows it created when two backends happened to share a database, which is an infrastructure bug, not an argument for centralisation.
- **Central persistence + `RemoteTaskClient`** (rev. 2, §2.9) — proposed 2026-07-07, **rejected 2026-07-27, never implemented in between.** Adds a synchronous HTTP + M2M-auth dependency to every other backend's task-recording hot path, makes control-plane a single point of failure for task visibility platform-wide, and hands it ownership of another service's operational data. Found to be unnecessary: `evaluation` has run fully isolated (its own dedicated database) since 2026-07-07 and never needed it — the actual bug (control-plane and knowledge-flow accidentally sharing one Postgres database, discovered via duplicate rows on the Activity page) is fixed by giving knowledge-flow the same isolation, at the infrastructure layer only. See the rev. 4 amendment at the top of this document and §2.9.
