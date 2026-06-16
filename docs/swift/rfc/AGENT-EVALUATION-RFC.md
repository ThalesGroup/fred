# RFC EVAL-01 — Fred Agent Evaluation Platform

**Status:** confirmed
**Version:** v3 — supersedes v1 (Dimitri) and v2 (Marc)
**Date:** 2026-06-11
**Track:** `EVAL-01`
**Authors:** Dimitri Tombroff (v1); Marc Fawaz (v2 amendment); Marc Fawaz (v3)
**Reviewers:** Fred architecture owner, Control Plane owner, Frontend owner, Runtime owner, Observability owner
**Backlog:** [`../backlog/AGENT-EVALUATION-BACKLOG.md`](../backlog/AGENT-EVALUATION-BACKLOG.md)

---

## 1. Decision requested

Approve a first-class Fred evaluation capability implemented as a **separate application**:

```text
apps/fred-evaluation-backend/
```

The decision requested is:

1. Fred evaluation is a dedicated backend app with its own API process, worker process, persistence, migrations, configuration, scoring dependencies, and optional telemetry exporters.
2. The Control Plane remains business-agnostic. It does not own evaluation campaigns, test cases, metric results, scorer profiles, evaluation worker logic, or MLflow/Langfuse export logic.
3. The Control Plane remains the authoritative platform service for identity, teams, permissions, runtime catalog, managed agent instances, and execution preparation.
4. Runtime agents continue to expose the existing evaluation execution surface:

   ```text
   POST /agents/evaluate
   ```

5. The evaluation backend calls `/agents/evaluate` on configured runtime pods and scores the resulting `EvalTrace`.
6. The frontend integrates with the evaluation backend, not with the CLI and not directly with runtime pods.
7. The existing `fred-deepeval-cli` logic is refactored into a reusable evaluator core consumed by the evaluation backend worker and by the CLI.
8. OpenTelemetry is supported as an optional vendor-neutral export path. It is not the canonical evaluation result store.
9. MLflow, Langfuse, or similar platforms are treated as downstream integrations, preferably through an OpenTelemetry Collector first.
10. The previous draft that placed the worker inside the Control Plane is not considered implemented and is not part of the baseline for this RFC.

---

## 2. Context

Fred already has several ingredients required for agent evaluation:

- deployed agent runtimes expose `/agents/evaluate`;
- `EvalTrace` and `EvalStep` describe agent execution traces;
- external `dt-agents` can be called through the same runtime pattern as built-in Fred agents;
- `fred-deepeval-cli` can call Fred agents and calculate evaluation results;
- the frontend can integrate multiple backend APIs;
- the Control Plane owns platform-level runtime discovery and managed instance metadata.

The missing piece is a product-grade evaluation service that:

- lets users create evaluation campaigns from the frontend;
- persists campaigns, test cases, scores, verdicts, and traces;
- runs long evaluations asynchronously;
- provides progress, cancellation, and result inspection;
- exports traces/results to external observability platforms when configured;
- does all of this without turning the Control Plane into a business-domain scoring service.

The architectural correction in this RFC is the introduction of a new backend application:

```text
apps/fred-evaluation-backend/
```

This keeps the domain-specific evaluation lifecycle isolated from generic platform control.

---

## 3. Problem

The current CLI is useful for local and CI workflows, but it is not a frontend-integrated product backend.

A productized evaluation platform needs:

- authenticated API access;
- team-scoped campaign ownership;
- controlled target selection;
- test-case validation;
- asynchronous execution;
- durable partial results;
- progress streaming;
- cancellation;
- retry handling;
- scorer configuration;
- result history;
- export integration;
- retention policy;
- privacy controls;
- side-effect controls.

Putting this logic inside the Control Plane would violate a clean platform/domain separation:

```text
Control Plane = platform facts and generic execution preparation
Evaluation Backend = evaluation business domain
```

The Control Plane should not know DeepEval, metric thresholds, dataset schemas, evaluator prompts, or Langfuse/MLflow export semantics.

---

## 4. Goals

The approved design must:

1. Add a dedicated evaluation backend application.
2. Keep the Control Plane business-agnostic.
3. Let the frontend create, start, monitor, inspect, and export evaluation campaigns.
4. Evaluate both built-in Fred agents and external runtime agents such as `dt-agents`.
5. Use `/agents/evaluate` as the runtime execution contract.
6. Reuse the existing `EvalTrace` contract.
7. Reuse scorer logic from `fred-deepeval-cli` through a shared library/core.
8. Keep DeepEval, LiteLLM, MLflow, Langfuse, and OpenTelemetry exporter dependencies out of `fred-runtime` and out of the Control Plane.
9. Persist canonical evaluation results inside the evaluation backend.
10. Support optional OTLP export through an OpenTelemetry Collector.
11. Provide strong defaults for security, privacy, cost, concurrency, and retention.

---

## 5. Non-goals

This RFC does not:

- implement evaluation logic inside the Control Plane;
- add DeepEval dependencies to `fred-runtime`;
- add scoring dependencies to the normal Control Plane image;
- make the CLI the production orchestration engine;
- let the browser call runtime pods directly;
- let the browser submit arbitrary runtime URLs;
- make MLflow, Langfuse, or OpenTelemetry the system of record;
- introduce prompt optimization;
- introduce scheduled regression gates in the MVP;
- introduce automatic dataset generation;
- define a general platform-wide OTLP tracing architecture;
- guarantee safe execution of side-effecting agents in production environments.

---

## 6. Architectural principle

The core principle is:

```text
Control Plane remains generic.
Evaluation Backend owns the evaluation domain.
Runtime agents own execution.
```

This creates a clean separation:

| Layer | Owns | Must not own |
| --- | --- | --- |
| Frontend | Evaluation UX, pages, forms, result views | secrets, runtime URLs, scoring execution |
| Evaluation Backend | campaigns, datasets, scoring, results, exports | platform identity source of truth |
| Control Plane | teams, permissions, catalog, managed instances, execution preparation | metrics, test cases, scoring profiles |
| Runtime Agents | `/agents/evaluate`, `EvalTrace`, real agent execution | batch scoring, campaign persistence |
| External Observability | traces, dashboards, customer analysis | Fred canonical evaluation state |

---

## 7. Proposed architecture

```text
┌──────────────────────────────────────────────────────────────┐
│ Fred Frontend                                                │
│ - Evaluation pages                                           │
│ - Campaign creation                                          │
│ - Dataset upload/edit                                        │
│ - Progress and results                                       │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               │ /evaluation/v1/*
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ Fred Evaluation Backend API                                  │
│ apps/fred-evaluation-backend                                 │
│ - Campaign API                                               │
│ - Dataset validation                                         │
│ - Result API                                                 │
│ - SSE progress endpoint                                      │
│ - Export API                                                 │
│ - Own DB migrations                                          │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               │ task queue / DB lease / Temporal
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ Fred Evaluation Worker                                       │
│ apps/fred-evaluation-backend                                 │
│ - Loads campaign                                             │
│ - Resolves target through Control Plane                      │
│ - Calls runtime /agents/evaluate                             │
│ - Runs structural checks and DeepEval metrics                │
│ - Persists case results                                      │
│ - Emits campaign events                                      │
│ - Optionally emits OTLP                                      │
└───────────────┬──────────────────────────┬───────────────────┘
                │                          │
                ▼                          ▼
┌────────────────────────────┐  ┌─────────────────────────────┐
│ fred-agents runtime         │  │ dt-agents runtime            │
│ POST /agents/evaluate       │  │ POST /agents/evaluate        │
└────────────────────────────┘  └─────────────────────────────┘

Optional export:

Fred Evaluation Worker
        │
        ▼
OpenTelemetry Collector
        │
        ├── MLflow
        ├── Langfuse
        ├── Tempo
        └── customer observability stack
```

---

## 8. Repository placement

Create a new app:

```text
apps/fred-evaluation-backend/
```

Recommended layout:

```text
apps/fred-evaluation-backend/
├── fred_evaluation_backend/
│   ├── __init__.py
│   ├── main.py
│   ├── main_worker.py
│   │
│   ├── config/
│   │   ├── __init__.py
│   │   └── models.py
│   │
│   ├── campaigns/
│   │   ├── __init__.py
│   │   ├── api.py
│   │   ├── models.py
│   │   ├── service.py
│   │   └── store.py
│   │
│   ├── datasets/
│   │   ├── __init__.py
│   │   ├── api.py
│   │   ├── models.py
│   │   └── validators.py
│   │
│   ├── execution/
│   │   ├── __init__.py
│   │   ├── agent_client.py
│   │   ├── control_plane_client.py
│   │   ├── runtime_resolver.py
│   │   └── session_factory.py
│   │
│   ├── scoring/
│   │   ├── __init__.py
│   │   ├── profiles.py
│   │   ├── structural_checks.py
│   │   ├── deepeval_adapter.py
│   │   └── result_builder.py
│   │
│   ├── workers/
│   │   ├── __init__.py
│   │   ├── workflow.py
│   │   ├── activities.py
│   │   └── runner.py
│   │
│   ├── telemetry/
│   │   ├── __init__.py
│   │   ├── otel_exporter.py
│   │   ├── redaction.py
│   │   └── exporters.py
│   │
│   └── migrations/
│       └── versions/
│
├── dockerfiles/
│   ├── Dockerfile-api
│   └── Dockerfile-worker
│
├── pyproject.toml
├── README.md
└── CLAUDE.md
```

The app has two deployable processes:

```text
fred-evaluation-api
fred-evaluation-worker
```

The API process exposes HTTP endpoints. The worker process runs campaign execution and scoring.

---

## 9. Why not Control Plane?

The Control Plane should remain the source of truth for platform metadata and access control. Evaluation is not platform metadata; it is an application capability.

The following belong in the Control Plane:

```text
- users
- teams
- roles
- permissions
- runtime catalog
- agent catalog
- managed agent instances
- execution preparation
- platform configuration
```

The following do not belong in the Control Plane:

```text
- evaluation campaigns
- test cases
- datasets
- metric thresholds
- scoring profiles
- DeepEval adapters
- evaluator prompts
- campaign verdicts
- MLflow/Langfuse export logic
- OTel evaluation-export policy
```

Keeping those domains separate prevents the Control Plane from becoming an unbounded application monolith.

---

## 10. Interaction with Control Plane

The evaluation backend depends on the Control Plane for generic platform capabilities.

Examples:

```text
GET  /control-plane/v1/runtime-catalog
GET  /control-plane/v1/agent-templates
GET  /control-plane/v1/agent-instances/{id}
POST /control-plane/v1/agent-instances/{id}/prepare-execution
```

The exact endpoint names should follow the existing Control Plane product contract.

The evaluation backend must not duplicate Control Plane ownership of:

- team membership;
- permission calculation;
- managed instance configuration;
- runtime base URL cataloging;
- execution grant preparation.

The evaluation backend may cache resolved platform metadata for a single campaign run, but the Control Plane remains authoritative.

---

## 11. Target resolution

The frontend submits controlled target identifiers, never URLs.

```python
class ManagedInstanceTarget(BaseModel):
    kind: Literal["managed_instance"]
    agent_instance_id: str

class RuntimeAgentTarget(BaseModel):
    kind: Literal["runtime_agent"]
    runtime_id: str
    agent_id: str
```

Resolution flow:

```text
Frontend
  -> Evaluation Backend
      -> Control Plane validates target access and resolves execution metadata
          -> Evaluation Backend calls runtime /agents/evaluate
```

The browser never receives:

- runtime base URLs;
- service credentials;
- execution grants;
- judge credentials;
- OTel headers;
- MLflow or Langfuse credentials.

---

## 12. Evaluation API

The evaluation backend exposes its own API surface.

Base path:

```text
/evaluation/v1
```

### 12.1 Create and start campaign

```http
POST /evaluation/v1/campaigns
```

Request:

```json
{
  "name": "Aegis regression — June 2026",
  "team_id": "team-42",
  "target": {
    "kind": "runtime_agent",
    "runtime_id": "dt-agents",
    "agent_id": "fred.dt.aegis.graph"
  },
  "dataset": {
    "name": "policy-regression",
    "version": "2026-06-11",
    "cases": [
      {
        "external_id": "policy-001",
        "input": "What is required before production deployment?",
        "expected_output": "A security validation must be completed.",
        "tags": ["deployment", "security"]
      }
    ]
  },
  "profile": "auto",
  "judge_profile_id": "judge.mistral.large",
  "execution": {
    "max_concurrency": 3,
    "case_timeout_seconds": 600
  }
}
```

Response:

```json
{
  "campaign_id": "eval-cmp-8d923",
  "run_id": "eval-run-c3711",
  "state": "pending"
}
```

Recommended response status:

```text
202 Accepted
```

### 12.2 Campaign list

```http
GET /evaluation/v1/campaigns?team_id=team-42&state=running
```

### 12.3 Campaign detail

```http
GET /evaluation/v1/campaigns/{campaign_id}
```

### 12.4 Case results

```http
GET /evaluation/v1/campaigns/{campaign_id}/cases
GET /evaluation/v1/campaigns/{campaign_id}/cases/{case_id}
```

### 12.5 Progress stream

```http
GET /evaluation/v1/campaigns/{campaign_id}/events
```

The evaluation backend may implement this directly or map it internally to a generic task/event store. It must not depend on Control Plane task business logic unless that task system is explicitly extracted as a reusable platform library.

### 12.6 Cancellation

```http
POST /evaluation/v1/campaigns/{campaign_id}/cancel
```

### 12.7 Export

Deferred from MVP, but the intended API is:

```http
GET /evaluation/v1/campaigns/{campaign_id}/export?format=json
GET /evaluation/v1/campaigns/{campaign_id}/export?format=csv
```

---

## 13. Frontend integration

Add a dedicated evaluation frontend slice:

```text
apps/frontend/src/slices/evaluation/evaluationApi.ts
```

Add pages:

```text
apps/frontend/src/pages/EvaluationCampaigns.tsx
apps/frontend/src/pages/EvaluationCampaignCreate.tsx
apps/frontend/src/pages/EvaluationCampaignDetail.tsx
```

Suggested routes:

```text
/monitoring/evaluations
/monitoring/evaluations/new
/monitoring/evaluations/:campaignId
```

The frontend talks to:

```text
/evaluation/v1/*
```

It may also call Control Plane read APIs for generic platform metadata if that is already how other pages discover agents. However, campaign creation and result inspection belong to the evaluation API.

---

## 14. Evaluation backend persistence

The evaluation backend owns its own persistence schema.

Suggested tables:

```text
evaluation_campaign
evaluation_run
evaluation_case
evaluation_case_result
evaluation_metric_result
evaluation_event
evaluation_export_delivery
```

The evaluation backend may use the same database server as other Fred services, but it owns its migrations and schema.

The Control Plane database schema is not extended with evaluation campaign tables.

---

## 15. Canonical result model

Fred evaluation results are product records, not telemetry.

```python
class EvaluationCampaign(BaseModel):
    schema_version: Literal["1"] = "1"
    campaign_id: str
    run_id: str
    name: str
    team_id: str
    created_by: str
    target: EvaluationTarget
    dataset_name: str
    dataset_version: str | None
    profile: str
    judge_profile_id: str
    operational_state: Literal[
        "pending", "running", "succeeded", "failed", "cancelled"
    ]
    verdict: Literal["pending", "passed", "failed", "inconclusive"]
    total_cases: int
    completed_cases: int
    passed_cases: int
    failed_cases: int
    execution_error_cases: int
    scoring_error_cases: int
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
```

```python
class EvaluationCaseResult(BaseModel):
    schema_version: Literal["1"] = "1"
    case_id: str
    campaign_id: str
    run_id: str
    external_id: str | None
    status: Literal["pending", "running", "completed", "error", "cancelled"]
    outcome: Literal[
        "success",
        "execution_error",
        "degraded",
        "hitl_blocked",
        "unknown",
    ]
    verdict: Literal["passed", "failed", "inconclusive"]
    input: str
    expected_output: str | None
    actual_output: str | None
    profile: str
    structural_checks: list[StructuralCheckResult]
    metrics: list[EvaluationMetricResult]
    latency_ms: int | None
    token_usage: dict[str, int] | None
    execution_error: str | None
    scoring_errors: list[EvaluationError]
    raw_trace_ref: str | None
    telemetry_trace_id: str | None
    started_at: datetime | None
    completed_at: datetime | None
```

```python
class EvaluationMetricResult(BaseModel):
    name: str
    provider: str
    score: float | None
    threshold: float | None
    verdict: Literal["passed", "failed", "skipped", "error"]
    explanation: str | None
    error: str | None
```

The evaluation backend persists skipped metrics and scoring errors explicitly. They must not disappear from campaign aggregates.

---

## 16. State semantics

The platform exposes separate dimensions:

| Dimension | Meaning |
| --- | --- |
| Operational state | Did the campaign run, fail operationally, or get cancelled? |
| Campaign verdict | Did the evaluated agent pass the configured quality policy? |
| Case status | Was this test case processed? |
| Agent outcome | Did the runtime return success, degraded output, HITL block, or execution error? |
| Metric verdict | Did the metric pass, fail, skip, or error? |

A campaign can have:

```text
operational_state = succeeded
verdict = failed
```

This means the evaluation process completed correctly, but the evaluated agent did not meet quality expectations.

---

## 17. Worker behavior

The worker executes the campaign asynchronously.

```text
load campaign
resolve target through Control Plane
validate target is evaluation-safe
for each case with bounded concurrency:
  create isolated session
  call runtime POST /agents/evaluate
  classify agent outcome
  run structural checks
  run scoring metrics
  persist case result
  emit campaign progress event
  optionally emit OTLP trace
compute campaign aggregates
persist campaign verdict
emit terminal progress event
```

The worker must:

- use unique run IDs;
- use one fresh session per case by default;
- support cancellation;
- persist completed cases immediately;
- avoid re-executing completed cases after restart;
- retry runtime execution and judge scoring separately;
- keep end-user bearer tokens out of persisted workflow history;
- obtain service credentials or execution grants server-side;
- enforce server-defined limits.

---

## 18. Dependency strategy

The evaluation backend API image should remain reasonably light. The worker image may include heavy scoring dependencies.

`apps/fred-evaluation-backend/pyproject.toml` should define optional extras:

```toml
[project.optional-dependencies]
scoring = [
  "deepeval>=...",
  "litellm>=..."
]

otel = [
  "opentelemetry-sdk>=...",
  "opentelemetry-exporter-otlp>=..."
]

worker = [
  "temporalio>=..."
]
```

Deployable images:

```text
fred-evaluation-api      -> installs default dependencies
fred-evaluation-worker   -> installs [scoring, worker, otel] as configured
```

`fred-runtime`, `fred-sdk`, and Control Plane default dependencies remain scorer-free.

---

## 19. Relationship with `fred-deepeval-cli`

The CLI remains useful for local development and CI, but it should not be the production orchestration boundary.

Refactor scoring logic into a reusable package/core:

```text
fred_deepeval_core/
  models.py
  evaluator.py
  profiles.py
  structural_checks.py
  judge_factory.py
  result_builder.py
```

The CLI becomes:

```text
CLI args -> fred_deepeval_core -> stdout JSON / human display
```

The evaluation worker becomes:

```text
campaign case -> fred_deepeval_core -> persisted EvaluationCaseResult
```

Both consume the same core. Neither should duplicate scoring logic.

---

## 20. OpenTelemetry export

OTel is useful for interoperability, but it is not the source of truth.

Canonical result:

```text
Evaluation Backend database
```

Optional export:

```text
Evaluation Worker -> OTLP -> OTel Collector -> MLflow / Langfuse / Tempo / vendor
```

The worker emits one trace per test case.

Recommended root span:

```text
fred.evaluation.case
```

Recommended attributes:

```text
fred.evaluation.schema.version
fred.evaluation.campaign.id
fred.evaluation.run.id
fred.evaluation.case.id
fred.evaluation.dataset.name
fred.evaluation.dataset.version
fred.evaluation.profile
fred.evaluation.verdict
fred.agent.id
fred.runtime.id
fred.agent.instance.id
fred.team.id
```

Default content policy:

| Data | Default |
| --- | --- |
| Campaign/case identifiers | enabled |
| Agent/runtime identifiers | enabled |
| Numeric scores | enabled |
| Verdicts | enabled |
| Latency and token counts | enabled |
| User input | disabled |
| Expected output | disabled |
| Actual output | disabled |
| Retrieval context | disabled |
| Raw trace | disabled |
| Metric explanations | disabled |

MLflow and Langfuse native adapters may be added later, but only as optional exporters behind a generic interface. They must not change the canonical Fred result schema.

---

## 21. Security

### 21.1 No arbitrary runtime URLs

The frontend submits controlled identifiers. The evaluation backend resolves targets through the Control Plane.

Rejected:

```json
{
  "base_url": "https://some-user-provided-runtime"
}
```

Accepted:

```json
{
  "kind": "runtime_agent",
  "runtime_id": "dt-agents",
  "agent_id": "fred.dt.aegis.graph"
}
```

### 21.2 Secrets

The frontend never receives:

- runtime credentials;
- execution grants;
- judge credentials;
- OTLP headers;
- MLflow credentials;
- Langfuse credentials.

The evaluation backend resolves secrets server-side.

### 21.3 Side effects

`/agents/evaluate` runs the real agent path. Tools may mutate external systems.

Therefore, evaluation is disabled by default unless:

- the deployment enables the evaluation backend;
- the target runtime or managed instance is marked evaluation-safe;
- the execution environment is approved for evaluation;
- side-effecting tool profiles are either blocked or explicitly allowed by policy.

### 21.4 Audit

The evaluation backend records:

- campaign creation;
- campaign cancellation;
- actor;
- team;
- target agent;
- runtime;
- judge profile ID;
- dataset name/version;
- configured case count;
- configured concurrency;
- terminal operational state;
- terminal verdict;
- export policy used.

---

## 22. Configuration

Example configuration:

```yaml
evaluation:
  enabled: false

  api:
    base_url: /evaluation/v1

  control_plane:
    base_url: http://control-plane-backend:8080/control-plane/v1
    credential_ref: EVALUATION_CONTROL_PLANE_TOKEN

  scheduler:
    backend: temporal
    task_queue: fred-evaluation

  limits:
    max_cases_per_campaign: 200
    default_max_concurrency: 3
    hard_max_concurrency: 10
    case_timeout_seconds: 600
    judge_timeout_seconds: 120
    input_max_bytes: 65536
    expected_output_max_bytes: 65536

  retention:
    result_days: 180
    raw_trace_days: 30

  judge_profiles:
    - id: judge.mistral.large
      provider: litellm
      model: mistral/mistral-large-latest
      credential_ref: MISTRAL_API_KEY

  telemetry:
    otlp:
      enabled: false
      endpoint: http://otel-collector:4318
      protocol: http/protobuf
      headers_secret_ref: EVALUATION_OTLP_HEADERS
      capture_content: false
```

---

## 23. Raw trace persistence

Raw `EvalTrace` payloads can be large and sensitive.

Recommended behavior:

- store summary fields in relational tables;
- store raw traces in object storage when configured;
- store only `raw_trace_ref` and content hash in relational storage;
- make raw trace persistence configurable;
- apply shorter retention to raw traces than to campaign summaries;
- redact or omit raw trace data from events and telemetry by default.

Local development may use bounded database JSON storage.

---

## 24. Frontend UX

### 24.1 Campaign list

Show:

- campaign name;
- target agent;
- runtime or managed instance;
- dataset;
- operational state;
- verdict;
- progress;
- pass rate;
- creator;
- creation/completion time.

### 24.2 New campaign wizard

Steps:

1. Target selection.
2. Dataset input.
3. Evaluation policy.

Dataset input modes:

- manual table;
- JSON upload;
- CSV upload.

### 24.3 Campaign detail

Show:

- progress stream;
- aggregate cards;
- metric summary;
- case table;
- filters by status/verdict/outcome/tag;
- case detail drawer;
- trace link when retained and authorized.

### 24.4 Safety UX

Before starting a campaign, the UI shows:

- target environment;
- whether the target is evaluation-safe;
- expected case count;
- max concurrency;
- approximate cost warning if judge profile exposes pricing metadata;
- privacy/export policy.

---

## 25. Implementation sequence

### Phase 0 — RFC and backlog convergence

1. Replace the current repository RFC with this proposal after approval.
2. Update the EVAL-01 backlog.
3. Update ID registry, track status, PMO board, and workplan references if required.
4. Add or update architectural contract docs for the new evaluation backend.

### Phase 1 — App skeleton

1. Create `apps/fred-evaluation-backend/`.
2. Add FastAPI application entrypoint.
3. Add worker entrypoint.
4. Add configuration model.
5. Add Dockerfiles for API and worker.
6. Add health endpoint.
7. Add repository-local `CLAUDE.md` if required by project convention.

### Phase 2 — Core contracts and persistence

1. Add campaign, run, case, metric, and event models.
2. Add migrations.
3. Add create/list/detail/case APIs.
4. Add OpenAPI generation.
5. Add frontend generated client.

### Phase 3 — Control Plane integration

1. Add a typed Control Plane client.
2. Resolve runtime targets.
3. Resolve managed instance targets.
4. Validate team access.
5. Prepare execution metadata server-side.
6. Reject arbitrary runtime URLs.

### Phase 4 — Evaluator core reuse

1. Extract reusable core from `fred-deepeval-cli`.
2. Add stable request/result schemas.
3. Add structural checks.
4. Add DeepEval adapter.
5. Keep CLI working as a thin adapter.

### Phase 5 — Worker execution

1. Add asynchronous campaign runner.
2. Add bounded concurrency.
3. Add cancellation.
4. Add per-case persistence.
5. Add retry policies.
6. Add progress events.
7. Add aggregate calculation.

### Phase 6 — Frontend

1. Add evaluation API slice.
2. Add campaign list page.
3. Add creation wizard.
4. Add campaign detail page.
5. Add result table and case detail drawer.
6. Add progress stream integration.

### Phase 7 — OTel export

1. Add optional OTel exporter in the worker.
2. Emit one trace per test case.
3. Add content redaction.
4. Add Collector integration example.
5. Persist telemetry trace IDs.

### Phase 8 — Hardening

1. Add side-effect safety controls.
2. Add retention jobs.
3. Add export API.
4. Add CSV/JSON dataset import validation.
5. Add live tests against `fred-agents` and `dt-agents`.
6. Add documentation.

---

## 26. Verification plan

### API tests

- create campaign;
- reject unknown runtime;
- reject arbitrary URL;
- reject unauthorized team;
- enforce case count and payload limits;
- list campaigns by team;
- fetch campaign detail;
- fetch paginated case results;
- cancel running campaign.

### Worker tests

- successful case;
- execution error;
- degraded result;
- HITL blocked;
- metric failure;
- scorer failure;
- partial campaign persistence;
- worker restart;
- cancellation;
- bounded concurrency.

### Control Plane integration tests

- runtime target resolution;
- managed instance resolution;
- team authorization;
- execution preparation;
- expired or invalid service credential behavior.

### Frontend tests

- campaign wizard validation;
- generated API types;
- progress stream reconnect;
- result filters;
- case detail drawer;
- permission-aware controls;
- safety warning display.

### OTel tests

- one trace per case;
- required correlation attributes;
- content disabled by default;
- export failure does not fail canonical persistence;
- telemetry trace ID persisted when export succeeds.

### Security tests

- no secrets in API responses;
- no runtime URLs exposed to browser;
- no judge credentials in logs;
- raw trace retention enforced;
- side-effecting targets rejected by default.

---

## 27. Alternatives considered

### A. Put evaluation worker inside Control Plane

Rejected. Evaluation is business-domain logic. It would pollute the Control Plane with scoring concerns, metric semantics, dataset lifecycle, and vendor-specific export policies.

### B. Execute `fred-deepeval-cli` from the frontend

Rejected. The browser cannot safely execute Python, protect credentials, or manage durable background work.

### C. Execute `fred-deepeval-cli` as a subprocess from a web handler

Rejected. Subprocess orchestration is brittle and makes partial persistence, cancellation, retries, and scaling harder.

### D. Put DeepEval in `fred-runtime`

Rejected. Runtime pods should remain lightweight execution surfaces and should not carry scoring dependencies.

### E. Store only OTel traces and use MLflow/Langfuse as the result UI

Rejected. Telemetry systems are not Fred's canonical business store. They are optional downstream integrations.

### F. Let the frontend call runtime pods directly

Rejected. It would expose runtime URLs and credentials and bypass Control Plane access rules.

### G. Add direct MLflow/Langfuse adapters first

Rejected for MVP. Start with OTLP through a Collector. Add native adapters later only if a concrete use case requires vendor-specific objects.

---

## 28. Impact on existing repository docs

After approval, update:

```text
docs/swift/rfc/AGENT-EVALUATION-RFC.md
docs/swift/backlog/AGENT-EVALUATION-BACKLOG.md
docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md
docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md
docs/swift/data/id-legend.yaml
docs/swift/tracks/README.md
docs/swift/WORKPLAN.md
docs/swift/PMO-BOARD.md
```

Required doc changes:

1. State that evaluation is a separate backend app.
2. State that Control Plane remains business-agnostic.
3. Freeze `/agents/evaluate` as the runtime execution contract.
4. Add the evaluation backend API contract.
5. Add the evaluation backend deployment model.
6. Add the optional OTLP export model.
7. Add security and side-effect policy.
8. Update backlog implementation phases.

---

## 29. Approval outcome

Approval means the team accepts:

- creation of `apps/fred-evaluation-backend/`;
- separation of evaluation domain logic from Control Plane;
- reuse of `/agents/evaluate`;
- reuse/refactor of `fred-deepeval-cli` scoring logic;
- dedicated API and worker images;
- canonical persistence in the evaluation backend;
- optional OTel export through a Collector;
- frontend integration through `/evaluation/v1/*`.

Implementation still requires the repository's normal developer confirmation, issue creation, branch creation, tests, and code-quality workflow.
