# Agent Evaluation — Implementation Backlog

**RFC**: [`docs/rfc/AGENT-EVALUATION-RFC.md`](../rfc/AGENT-EVALUATION-RFC.md)

**Status**: Implementation started — EvalTrace HTTP path and external CLI prototype already exist

**Why this track exists**: Fred now has the first building blocks for external agent evaluation (`/agents/evaluate`, `EvalTrace`, and an external CLI prototype), but the RFC goal is broader: to build a durable, industrializable validation toolchain driven by datasets, execution traces, and external scoring tools, rather than in-process evaluators or one class per agent. This backlog tracks the remaining work to turn that strategy into a first-class validation surface.

---

## 0 Overview

### 0.1 Goal

Introduce a first-class agent evaluation toolchain for Fred that:

- evaluates agents through the same HTTP surface used in production
- captures a stable structured execution trace (`EvalTrace`)
- keeps scoring outside `fred-runtime`
- supports dataset-driven validation instead of one evaluator class per agent
- validates not only final text output, but also tool usage, retrieval grounding, failure modes, and latency/cost signals

This toolchain must make it easy to answer questions such as:

- did the agent answer correctly?
- did it call the expected tools?
- did it ground its answer in the retrieved context?
- did it degrade gracefully on failures?
- did a change regress behavior compared with a known baseline?

---

### 0.2 Why this matters

Today Fred has the core ingredients for evaluation, but not yet a complete validation product:

- `fred-runtime` knows how to execute and stream events
- agents already emit enough protocol information to derive an evaluation trace
- `/agents/evaluate` now exposes that trace directly in structured form
- an external CLI prototype (`fred-deepeval-cli`) can already evaluate and score one turn

What is still missing is the industrialized layer:

- stable datasets
- configurable validation profiles by agent type
- structured checks for tool usage and retrieval quality
- robust scoring workflows
- batch execution and baseline comparison
- documentation and team ergonomics

Without this layer, validation remains ad hoc and does not scale well across many agents.

---

### 0.3 Core decision

Keep the architecture split defined in the RFC:

1. `fred-runtime` owns execution and trace production
2. external tooling owns scoring, datasets, and reporting
3. agent-specific variability lives in datasets and validation profiles, not in one Python evaluator class per agent

This preserves the architectural rule:

- execution belongs to Fred
- scoring does not

---

## 1 Design rules

### 1.1 Evaluate through HTTP only

All validation flows must use the deployed/runtime HTTP path. No in-process evaluators should be introduced for this track.

### 1.2 EvalTrace is the evaluation unit

The primary artifact is not only the final text output, but the full execution trace. Validation logic must be able to inspect:

- `output`
- `error`
- `steps`
- `tools_called`
- `retrieval_context`
- `latency_ms`
- `token_usage`

### 1.3 Variability lives in datasets and profiles

Adding a new agent to the validation surface should require:

- a dataset
- optionally a validation profile

It must not require a new Python evaluator class.

### 1.4 No heavy scoring dependencies in `fred-runtime`

`fred-runtime` may contribute trace and protocol helpers, but not DeepEval, Promptfoo, HTML reporting, or other heavy scoring stacks.

---

## 2 Current implementation status

Shipped pieces:

- `POST /agents/evaluate` exists
- the `EvalTrace` contract exists and includes `steps`, `tools_called`, and `retrieval_context`
- `AgentPodClient.evaluate()` exists in `fred-runtime`
- `fred-deepeval-cli` exists as a standalone external project
- the CLI supports:
  - `evaluate`
  - outcome classification (`success`, `execution_error`, `degraded`, `hitl_blocked`)
  - `score`
- initial DeepEval integration works with a configurable judge model
- Makefile alignment with Fred conventions is in place
- unit tests exist for:
  - classification
  - CLI command flow
  - `EvalTrace -> LLMTestCase` adaptation

Remaining work before this track is considered complete:

- stabilize and document the evaluation contract
- add validation profiles and dataset-driven execution
- add structural checks beyond LLM-as-a-judge scoring
- define recommended metrics by agent type
- support batch execution and baseline workflows
- validate against real sample agents and realistic non-happy-path scenarios

---

## 3.0 Completed work (v1 phases A–B)

The following items from the v1 plan were delivered before this backlog was restructured to RFC v2.

### Phase A — Runtime trace surface
- [x] `EvalTrace` contract exists with `steps`, `tools_called`, `retrieval_context`
- [x] `POST /agents/evaluate` exposed and stable
- [x] `AgentPodClient.evaluate()` exists in `fred-runtime`

### Phase B — External CLI foundation
- [x] `fred-deepeval-cli` prototype exists with `evaluate` and `score` commands
- [x] Outcome classification (`success`, `execution_error`, `degraded`, `hitl_blocked`)
- [x] DeepEval integration with configurable judge model
- [x] Unit tests for classification, CLI flow, `EvalTrace → LLMTestCase` adaptation

## 3 Implementation plan

### Phase 0 — Docs & contracts convergence

- [x] Replace RFC v1 with approved RFC v2 text in `docs/swift/rfc/AGENT-EVALUATION-RFC.md`
- [x] Update `id-legend.yaml`: add backlog ref, change status to `in_progress`
- [x] Update `tracks/README.md`: EVAL-01 → In progress
- [x] Update `WORKPLAN.md`: fix RFC path, reflect delivered foundations
- [x] Update `PMO-BOARD.md`: add EVAL backlog link
- [x] Freeze `POST /agents/evaluate` and `EvalTrace` in `RUNTIME-EXECUTION-CONTRACT.md`
- [x] Add evaluation API surface to `CONTROL-PLANE-PRODUCT-CONTRACT.md`
- [x] Add `EvaluationTaskEvent` and `EvaluationDetail` to `TASK-EVENT-STREAM-RFC.md`

---

### EVAL-03 — Service-agent execution authorization (Solution A)

RFC: `fred-agent-evaluator/docs/rfc/EVAL-AUTH-RFC.md`. Branch `1885`. The async worker
authenticates as the `fred-evaluation-worker` service client (`service_agent` role only)
and must be authorized for execution scoped to the request `team_id`, read-only, with
**no OpenFGA tuple** (Solution A). Identity provisioning is done in fred-deployment-factory.

- [x] `fred-core`: `is_service_agent()` helper + `SERVICE_AGENT_ALLOWED_TEAM_PERMISSIONS` (`{CAN_READ}` only)
- [x] `fred-runtime`: recognize `service_agent` in `_authorize_execution_or_raise` (scoped to `team_id`, audited, fail-closed if no team)
- [x] `control-plane`: recognize `service_agent` in `_validate_team_and_check_permission` (read-only; write permissions fall through to the normal ReBAC check → denied)
- [x] Tests: allow/deny in fred-core, fred-runtime, control-plane
- [x] Point the worker M2M identity to `fred-evaluation-worker` (fred-agent-evaluator branch `21`)

---

### Phase 1 — Reusable evaluator core (`fred-deepeval-cli`)

- [ ] Restructure package into `core/`, `cli/`, `worker_adapter.py`
- [ ] Extract typed models: `EvaluationCaseRequest`, `EvaluationCaseResult`, `EvaluationMetricResult` with stable schema version
- [ ] Expose public entrypoint `evaluate_case(request, *, execution_client, judge) -> EvaluationCaseResult`
- [ ] Extract `judge_factory.py` — provider-agnostic, profile-driven (LiteLLM, OpenAI)
- [ ] Separate execution result, structural checks, metric results, and scoring errors explicitly
- [ ] Keep CLI as a thin adapter over the core
- [ ] Add unit tests: profiles, structural checks, scorer failures, serialization

---

### Phase 2 — Campaign resource & Control Plane API

- [ ] Add `apps/control-plane-backend/control_plane_backend/evaluations/` module
- [ ] `models.py` — `EvaluationCampaign`, `EvaluationCaseResult`, `EvaluationTarget` (discriminated union)
- [ ] `store.py` — PostgreSQL persistence: `evaluation_campaign`, `evaluation_case`, `evaluation_metric_result`
- [ ] `service.py` — campaign validation, target resolution (runtime catalog + managed instances), authorization
- [ ] `api.py` — endpoints: `POST /control-plane/v1/evaluation-campaigns`, `GET` list/detail/cases
- [ ] Database migrations
- [ ] Enforce strict server-side limits (max cases, concurrency, timeouts, payload sizes)
- [ ] Reuse existing team permissions (`CAN_READ`, `CAN_UPDATE_AGENTS`) — no new ReBAC relations in MVP
- [ ] Regenerate Control Plane OpenAPI and frontend generated client

---

### Phase 3 — Evaluation worker & task events

- [ ] Add `EvaluationTaskEvent` and `EvaluationDetail` to `fred_core/tasks/models.py`
- [ ] Add `worker.py` — campaign workflow, bounded parallel execution, per-case persistence
- [ ] Add `workflow.py` — Temporal integration (unique workflow ID per `campaign_id`, cooperative cancellation)
- [ ] Independent retry policies for agent execution, judge calls, and persistence
- [ ] Idempotent case persistence: key on `(campaign_id, case_id, attempt)`
- [ ] Campaign aggregate calculation repeatable from persisted case records
- [ ] Bearer tokens and judge secrets never in Temporal workflow history
- [ ] Separate Docker image for the worker with evaluation extras (DeepEval, LiteLLM, Temporal deps)
- [ ] Local in-memory runner for tests and dev mode

---

### Phase 4 — Frontend

- [ ] Add routes: `/monitoring/evaluations`, `/monitoring/evaluations/new`, `/monitoring/evaluations/:campaignId`
- [ ] Campaign creation — 3-step form: target, dataset (manual / JSON / CSV), evaluation policy
- [ ] Campaign list — name, target agent, dataset name/version, operational state, verdict, progress, pass rate
- [ ] Campaign detail — shared SSE task manager, aggregate metric cards, paginated case table
- [ ] Case detail drawer — input, expected output, actual output, structural checks, metric scores/reasons, latency, tokens, errors
- [ ] Permission-aware controls and side-effect warning before start
- [ ] All request/response types from generated OpenAPI — no hand-written TypeScript duplicates
- [ ] Reuse patterns from `ProcessorBench.tsx`, `ProcessorRunDetail.tsx`, `rework/features/tasks`

---

### Phase 5 — Optional OTel export

- [ ] Add OTel SDK as optional dependency of the worker image only
- [ ] Emit one trace per test case with `fred.evaluation.*` correlation attributes
- [ ] Content redaction off by default (inputs, outputs, explanations not exported)
- [ ] Persist `telemetry_trace_id` on case result when export succeeds
- [ ] Export failure must not fail or rollback canonical campaign persistence
- [ ] Validate export via OTel Collector to at least one downstream backend (MLflow or Langfuse)
- [ ] Add `evaluation.telemetry.otlp` config block to worker configuration

---

### Phase 6 — Live validation & hardening

- [ ] Validate one `fred-agents` target end-to-end
- [ ] Validate one external `dt-agents` target
- [ ] Run with Keycloak enabled
- [ ] Test campaign cancellation
- [ ] Test OTel Collector export
- [ ] Test side-effect policy rejection (blocked by default)
- [ ] Document dataset authoring and failure diagnosis

---

### EVAL-02 — Task-event adoption (standalone evaluator)

RFC: [`AGENT-EVALUATION-TASK-EVENT-AMENDMENT-RFC.md`](../rfc/AGENT-EVALUATION-TASK-EVENT-AMENDMENT-RFC.md).
Refines Phases 3–4 for the deployed reality: the evaluator ships as a **standalone service**
(own `/evaluation/v1` surface), not inside the control-plane (EVAL-01 §8.3). The `/rework`
evaluation UI is already built (Phase 4 UI) against a **bespoke** campaign SSE; this is the
cutover to canonical task events.

- [ ] `fred-core` 3.1.1 → 3.2.0: implement the `evaluation` kind (`EvaluationDetail`,
      `EvaluationTaskEvent`, `StartEvaluationParams`/`Request`, extend unions) per OPS-04 §2.1/§2.5
- [ ] Evaluator: wire `fred_core.tasks` (`TaskService`, `PostgresEventBus`, `TaskStore`,
      `TemporalWorkflowControl`); workflow emits campaign-level `TaskEvent`; execution binding +
      reconcile sweeper; `target={type:"evaluation_campaign",…}`, `team_id`
- [ ] Evaluator: mount `POST/GET /evaluation/v1/tasks`, `GET …/tasks/{id}/events`,
      `POST …/tasks/{id}/cancel`; add `task_run` + `task_event_log` migrations; remove bespoke SSE
- [ ] Frontend: regenerate evaluation slice (now carries `/tasks*` + `evaluation` `TaskEvent`)
- [ ] Frontend: make `useTaskRehydration` + `useTaskSseManager` **multi-source** (knowledge-flow +
      control-plane + evaluation); add `evaluation` to `taskKinds`/labels
- [ ] Frontend: cut over the `EvaluationCampaignDetail` **SEAM** (bespoke SSE → `useTaskStream` →
      `TaskStateBadge`/`TaskProgressBar`); surface campaigns in `TaskTray` + inline `TaskIndicator`
- [ ] **Cross-repo codegen guard**: CI check asserting the frontend's vendored
      `src/slices/evaluation/openapi.json` matches the `fred-agent-evaluator` published OpenAPI for
      the pinned evaluator/fred-core version (turns silent client drift into a failing build).
      Provenance + regen procedure: `apps/frontend/src/slices/evaluation/README.md`.

---

## 4 Resolved decisions

| Decision | Chosen answer |
| --- | --- |
| Execution path | `POST /agents/evaluate` — HTTP only, no direct class instantiation |
| Evaluation unit | `EvalTrace` typed contract |
| Browser integration boundary | Control Plane product API — never CLI subprocess or raw runtime URLs |
| Long-running execution | Existing task framework + separate evaluation worker |
| Scoring implementation | Reusable external core; DeepEval first |
| Heavy dependency placement | Evaluation worker image only — not fred-runtime, not Control Plane web image |
| Canonical result storage | Fred Control Plane PostgreSQL persistence |
| Telemetry role | Optional correlated export, not source of truth |
| Vendor integration | OTel Collector first; native adapters deferred |
| Runtime target selection | Catalog IDs / managed instance IDs only — no frontend-supplied URLs |
| Authorization | Existing team permissions; no new ReBAC relation in MVP |
| Side-effect policy | Denied by default unless explicitly evaluation-safe |
| CLI | Kept as thin adapter over the same reusable core |
| Promptfoo / Inspect AI | Optional external tools, not the Fred UI architecture |

---

## 5 Open questions

All previously open questions are resolved by RFC v2. See `docs/swift/rfc/AGENT-EVALUATION-RFC.md §24`.

---

## 6 Progress

| Phase | Status | Notes |
| --- | --- | --- |
| Phase 0 — Docs & contracts | In progress | This issue |
| Phase 1 — CLI core extraction | Not started | `fred-deepeval-cli` repo |
| Phase 2 — Campaign API | Not started | Depends on Phase 0 |
| Phase 3 — Evaluation worker | Not started | Depends on Phase 1 + 2 |
| Phase 4 — Frontend | Not started | Depends on Phase 2 + 3 |
| Phase 5 — OTel export | Not started | Depends on Phase 3 |
| EVAL-02 — Task-event adoption | Proposed | RFC EVAL-02; standalone evaluator + multi-source tray |
| Phase 6 — Live validation | Not started | Depends on Phase 3 + 4 |