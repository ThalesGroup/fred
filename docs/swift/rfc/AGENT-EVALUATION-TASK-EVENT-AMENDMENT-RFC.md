# RFC EVAL-02 — Evaluator task-event adoption (standalone deployment)

**ID:** EVAL-02
**Status:** proposed — awaiting confirmation
**Author:** Dimitri Tombroff
**Date:** 2026-06-24
**Amends:** [`AGENT-EVALUATION-RFC.md`](AGENT-EVALUATION-RFC.md) (EVAL-01) §8, §10 · [`TASK-EVENT-STREAM-RFC.md`](TASK-EVENT-STREAM-RFC.md) (OPS-04) §2.1, §2.5, §5
**Backlog:** [`../backlog/AGENT-EVALUATION-BACKLOG.md`](../backlog/AGENT-EVALUATION-BACKLOG.md)

---

## 1. Why this amendment

The task-event design for evaluation is **already confirmed**: OPS-04 §2.1/§2.5/§5 defines
the `evaluation` kind (`EvaluationDetail`, `EvaluationTaskEvent`, the `evaluation` consumer),
and EVAL-01 §10 specifies the `fred_core.tasks.models` extension, the `evaluation_campaign`
target, the team-scope read rule (§8.4), and the content boundary. This RFC does **not**
redesign any of that. It records three facts that postdate those RFCs and the implementation
plan that follows from them:

1. **Deployment delta.** EVAL-01 §8.3 assumed evaluation lives *inside the control-plane*
   (`/control-plane/v1/tasks/{id}/events`). The component actually built (Odelia's
   `fred-agent-evaluator`) is a **standalone service** with its own `/evaluation/v1` surface,
   currently using a **bespoke** `/evaluation/v1/campaigns/{id}/events` SSE and bespoke
   campaign-state fields — i.e. exactly the "third pattern" OPS-04 §1 exists to prevent.
2. **Implementation gap.** `fred-core` 3.1.1 (`libs/fred-core`) ships only the `ingestion`
   and `log` kinds. The `evaluation` kind (and `migration`) are specified-not-built.
3. **Frontend gap.** The task tray is single-source: `useTaskRehydration` fetches
   `/knowledge-flow/v1/tasks?scope=user` and `useTaskSseManager` defaults to
   `/knowledge-flow/v1`. It cannot yet surface a third producer.

The frontend evaluation UI has already been rebuilt on the `/rework` design system with an
explicit **SEAM** in `EvaluationCampaignDetail` (bespoke SSE + `StatusPill`/`ProgressBar`)
marking where the canonical task components bind once this lands.

## 2. Decisions

**D1 — The standalone evaluator owns its task surface.** It mounts the canonical OPS-04 §2.7
endpoints under its own prefix:

```
POST /evaluation/v1/tasks                 StartEvaluationRequest → 202 { task_id }
GET  /evaluation/v1/tasks                 ?scope=user|team&team_id= → TaskSummary[]
GET  /evaluation/v1/tasks/{id}/events     text/event-stream of TaskEvent (Last-Event-ID replay)
POST /evaluation/v1/tasks/{id}/cancel     202 (idempotent)
```

The bespoke `/evaluation/v1/campaigns/{id}/events` SSE is removed once the UI cuts over.
(Rejected: routing through control-plane per EVAL-01 §8.3 — the evaluator is deployed and
scaled independently; proxying its task stream through the control-plane couples two services
for no benefit now that fred-core makes the surface reusable.)

**D2 — Two planes, kept distinct** (reaffirming OPS-04 + EVAL-01):
- **Task-event plane** = the *execution facet* of one campaign **run**: `TaskState`
  (`pending/running/succeeded/failed/cancelled`), `progress = completed/total`, `step`,
  cancel, reconciliation, global tray. One task per run.
- **Evaluation domain plane** = the *substance*: campaigns list/history, **verdict**, per-case
  results, metrics, analysis, scheduling. Stays in the evaluation domain API.
- The campaigns **list stays domain-backed** (it is not the task list); the tray surfaces
  in-flight runs; Detail composes both.

**D3 — Three traps to honour in implementation:**
- Task `succeeded` ≠ evaluation `verdict`. "Run finished" and "agents passed" are orthogonal;
  the UI shows both and never overloads task-state with quality.
- The task is **campaign-level only**. Per-case results stay domain; at most `TaskLogEvent`
  narrates steps. `EvaluationDetail` carries compact counters only (OPS-04 §2.1, EVAL-01 §10).
- Scheduling/recurrence is a scheduler concept, not a task state. A task = one execution;
  the schedule spawns tasks.

## 3. Implementation sequence

1. **fred-core** (`libs/fred-core`, 3.1.1 → 3.2.0): implement the `evaluation` kind exactly per
   OPS-04 §2.1/§2.5 + EVAL-01 §10 — `EvaluationDetail`, `EvaluationTaskEvent`,
   `StartEvaluationParams`/`StartEvaluationRequest`, extend the `TaskEvent` and
   `StartTaskRequest` unions. `make openapi`. Publish; repin the evaluator + control-plane.
2. **Evaluator backend** (`fred-agent-evaluator`): wire `fred_core.tasks` — `TaskService`,
   `PostgresEventBus`, `TaskStore`, `TemporalWorkflowControl` (the evaluator already runs on
   Temporal + Postgres). The campaign-execution workflow emits `TaskEvent` via `ctx.emit`
   (campaign-level counters per `EvaluationDetail`); pre-generate the execution binding
   (OPS-04 §2.8); add the reconcile sweeper; set `target = {type:"evaluation_campaign", …}`
   and `team_id`. Mount the §2-D1 router. Add `task_run` + `task_event_log` migrations to the
   `evaluation` DB. Remove the bespoke campaign SSE.
3. **Frontend codegen**: regenerate the evaluation slice from the evaluator OpenAPI (now
   carrying `/tasks*` + the `evaluation` `TaskEvent` variant).
4. **Frontend tray → multi-source**: make `useTaskRehydration` + `useTaskSseManager` aggregate
   across producers (knowledge-flow + control-plane + **evaluation**) by base path. Add the
   `evaluation` kind to `taskKinds`/labels.
5. **Cut over the Detail SEAM**: replace the bespoke SSE + `StatusPill`/`ProgressBar` with the
   canonical `useTaskStream` → `TaskStateBadge`/`TaskProgressBar`; surface campaigns in the
   global `TaskTray` and inline `TaskIndicator` on campaign rows. Keep verdict/metrics/cases
   on the domain plane (D2).

## 4. Impact

- `libs/fred-core` — implement the `evaluation` kind (and the generic task router/SSE wiring
  the standalone evaluator mounts, per OPS-04 §2.7); minor version bump.
- `fred-agent-evaluator` — task-event production + endpoints + migrations; remove bespoke SSE.
- `apps/frontend` — multi-source tray; eval slice regen; Detail/list seam cutover.
- Frozen contracts — none. Task endpoints are product/admin surface (OPS-04 §6); the evaluator's
  `/evaluation/v1/tasks*` mirror the canonical shape.

### 4.1 Cross-repo codegen provenance (known risk, accepted for this release)

The frontend evaluation slice (`apps/frontend/src/slices/evaluation/`) is generated from
the **`fred-agent-evaluator`** OpenAPI — a **separate repository** under `ignored/` that
deploys independently. Unlike the control-plane / knowledge-flow slices (first-party
backends), this is an external component feeding generated client code into the main repo.

Mitigation in place: we **vendor a pinned `openapi.json` snapshot** into the frontend and
generate from it (reproducible, and every API change is a reviewable diff), never against a
live/external path. Residual risk: **no CI check verifies the snapshot matches the deployed
evaluator**, so the client can silently drift if the snapshot is not refreshed. Procedure,
ownership, and regen steps are documented in
[`apps/frontend/src/slices/evaluation/README.md`](../../../apps/frontend/src/slices/evaluation/README.md).
**Follow-up:** a CI guard asserting snapshot == evaluator published OpenAPI for the pinned
version (tracked under EVAL-02 backlog).

## 5. Alternatives considered

- **Keep the bespoke campaign SSE** — rejected; it is the divergent third pattern OPS-04 §1
  exists to remove, and it forfeits the tray, reconciliation, and `Last-Event-ID` replay.
- **Reuse the `ingestion` kind** — rejected; semantically wrong and OPS-04/EVAL-01 already
  reserve `evaluation`.
- **Route tasks through the control-plane** (EVAL-01 §8.3 original) — rejected for the
  standalone deployment (D1).
