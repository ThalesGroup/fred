# RFC EVAL-01 — Fred Agent Evaluation Platform

**Status:** confirmed
**Version:** v2 proposal; supersedes the architecture and implementation sequence in v1  
**Date:** 2026-06-09  
**Authors:** Dimitri Tombroff (v1); Marc (v2 amendment proposal)  
**Reviewers:** Control Plane owner, Frontend owner, Runtime owner, Observability owner  
**Track:** `EVAL-01`  
**Backlog:** [`../backlog/AGENT-EVALUATION-BACKLOG.md`](../backlog/AGENT-EVALUATION-BACKLOG.md)

---

## 1. Decision requested

Approve a first-class Fred evaluation platform with the following boundaries:

1. The browser submits datasets and reads results through the Control Plane. It never executes the CLI and never receives runtime base URLs, service tokens, judge credentials, or telemetry credentials.
2. The Control Plane owns evaluation campaign authorization, runtime target resolution, task lifecycle, canonical result persistence, and the product API consumed by the frontend.
3. A separate evaluation worker performs agent execution and scoring. It reuses a library-quality core extracted from `fred-deepeval-cli`; DeepEval and other heavy scoring dependencies remain outside `fred-runtime` and outside the Control Plane web image.
4. The existing `POST /agents/evaluate` endpoint and typed `EvalTrace` remain the runtime execution contract. No second runtime evaluation endpoint is introduced.
5. Long-running evaluation uses the existing unified task event stream with a new `kind="evaluation"` variant.
6. OpenTelemetry is an optional export and interoperability layer emitted by the evaluation worker. Fred's persisted campaign result is the system of record. OTLP must not become the only result store.
7. MLflow, Langfuse, or other vendor backends are reached through an OpenTelemetry Collector where possible. Direct vendor-native adapters are deferred unless a proven requirement cannot be met through OTLP.
8. Evaluation of agents capable of side effects is denied by default unless the target is explicitly approved for evaluation or runs in an isolated evaluation environment.

Approval of this RFC authorizes contract and backlog updates. It does not authorize implementation until the repository's developer-confirmation and GitHub-issue steps are completed.

---

## 2. Why v2 is required

The existing v1 RFC correctly established two durable principles:

- evaluate deployed agents through HTTP rather than in-process bootstrap;
- keep heavy scorer dependencies out of `fred-runtime`.

Its proposed implementation is now stale. It assumes Fred must collect SSE events and proposes Promptfoo as the primary harness. The repository and external evaluation project have progressed beyond that design:

- `fred-sdk` contains typed `EvalTrace` and `EvalStep` contracts;
- `fred-runtime` exposes `POST /agents/evaluate`;
- `AgentPodClient.evaluate()` consumes that synchronous trace endpoint;
- `fred-deepeval-cli` can execute and score Fred agents through `/agents/evaluate`;
- the CLI contains initial dataset, structural-check, preset, and Temporal prototypes;
- the Control Plane has runtime catalog sources and managed-agent execution preparation;
- Fred has a persisted, reconnectable task/SSE framework;
- the frontend already has reusable benchmark-run and task-progress patterns.

The missing decision is no longer how to obtain an evaluation trace. The missing decision is how to productize evaluation safely for browser users while retaining an external, replaceable scoring engine.

This v2 proposal replaces the v1 architecture and implementation sequence while preserving its valid dependency and HTTP-execution constraints.

---

## 3. Problem

The current CLI is a developer tool, not a product backend. A browser integration needs capabilities that a command-line process does not provide:

- authenticated, team-scoped campaign creation;
- controlled agent selection without arbitrary URLs;
- test-case validation and size limits;
- long-running execution that survives browser disconnects;
- incremental progress and cancellation;
- persisted partial results;
- result history and comparison;
- separation of execution failures from scoring failures;
- protection of judge credentials and runtime credentials;
- multi-tenant authorization;
- export to customer observability platforms without making one vendor authoritative.

Launching `fred-deepeval-cli` as a subprocess from a React application or a synchronous HTTP handler would create an unsafe and unreliable architecture. It would also make cancellation, retries, identity propagation, partial persistence, and horizontal scaling difficult.

---

## 4. Goals

The approved design must:

1. Let a user select a Fred agent, submit test cases, start an evaluation, observe progress, and inspect results in the frontend.
2. Evaluate both agents packaged under `apps/fred-agents` and agents exposed by configured external runtime pods such as `dt-agents`.
3. Use the deployed `POST /agents/evaluate` HTTP path.
4. Preserve `EvalTrace` as the execution artifact used by structural checks and scorer adapters.
5. Keep agent-specific variability in datasets and validation profiles rather than one evaluator class per agent.
6. Persist a stable, versioned, vendor-neutral result contract.
7. Reuse the Control Plane's runtime catalog, team authorization, task event stream, scheduler, and persistence conventions.
8. Keep DeepEval, LiteLLM, Temporal evaluation activities, and OpenTelemetry exporters out of `fred-runtime`.
9. Support optional OTLP export to a customer-managed collector.
10. Enforce limits for concurrency, test-case count, execution timeout, scoring timeout, and payload retention.

---

## 5. Non-goals

This RFC does not:

- add DeepEval or OpenTelemetry dependencies to `fred-runtime`;
- replace the existing runtime tracer backends (`null`, `logging`, `langfuse`);
- introduce platform-wide `TracerBackend.otlp` or `MetricsBackend.otlp` support;
- make MLflow, Langfuse, DeepEval, or Promptfoo the Fred system of record;
- define automatic prompt optimization;
- define model-provider benchmarking unrelated to an agent execution trace;
- permit arbitrary runtime `base_url` values supplied by the frontend;
- guarantee safe evaluation of side-effecting tools against production systems;
- implement scheduled evaluation, pull-request quality gates, or cross-run statistical comparison in the MVP;
- remove the existing local CLI workflow.

Platform-wide OTLP support remains a separate observability decision. This RFC only permits OTLP emission from the isolated evaluation worker.

---

## 6. Design principles

### P1 — Production-path execution

Every case calls the same authenticated runtime path used by the deployed agent. The evaluation worker must not instantiate agent classes directly.

### P2 — Fred owns orchestration; scorer libraries own metric implementation

Fred owns the product resource, authorization, target resolution, scheduling, persistence, and UI contract. DeepEval or another external scorer owns metric calculation and judge interaction.

### P3 — Canonical results are not telemetry

Evaluation campaigns, cases, thresholds, verdicts, skipped metrics, and audit metadata are business records. They are persisted by Fred. OpenTelemetry is a correlated export, not the authoritative database.

### P4 — One task, many durable case results

A campaign is one long-running task. Each case is persisted independently as soon as execution and scoring finish. A worker crash must not erase already completed results.

### P5 — Operational state is different from quality verdict

A task can complete successfully while the evaluation verdict is failed. The platform must not conflate execution of the campaign with quality of the evaluated agent.

### P6 — Safe defaults

Raw prompts, outputs, expected answers, and retrieval context are not exported through telemetry by default. Side-effecting targets are blocked by default. Concurrency and dataset size are bounded.

### P7 — Extend existing contracts

The implementation extends the current runtime contract, Control Plane product contract, task event RFC, and EVAL-01 backlog. It does not create parallel task, routing, or authorization abstractions.

---

## 7. Proposed architecture

```text
┌──────────────────────────────────────────────────────────────┐
│ Fred Frontend                                                │
│ - create campaign                                            │
│ - upload/edit cases                                          │
│ - view task progress                                         │
│ - inspect persisted results                                  │
└──────────────────────────────┬───────────────────────────────┘
                               │ Control Plane API + task SSE
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ Control Plane web process                                    │
│ - OIDC / ReBAC                                                │
│ - runtime and managed-instance resolution                    │
│ - campaign validation and persistence                        │
│ - task creation and result queries                           │
│ - no DeepEval dependency                                     │
└──────────────────────────────┬───────────────────────────────┘
                               │ shared task store / scheduler
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ Control Plane evaluation worker — separate process/image     │
│ - campaign workflow and bounded parallelism                  │
│ - imports reusable fred-deepeval core                        │
│ - calls POST /agents/evaluate                                │
│ - runs structural checks and scorer adapters                 │
│ - persists each case and emits task events                   │
│ - optionally emits OTLP                                      │
└───────────────┬──────────────────────────┬───────────────────┘
                │                          │
                ▼                          ▼
       fred-agents runtime           dt-agents runtime
       POST /agents/evaluate         POST /agents/evaluate
                │
                ▼
       Judge provider through
       server-side judge profile

Optional export:
Evaluation worker → OTLP/HTTP → customer OTel Collector → MLflow / Langfuse / other sinks
```

### 7.1 Component ownership

| Concern | Owner |
| --- | --- |
| Agent execution and `EvalTrace` production | `fred-runtime` |
| Runtime and managed-instance discovery | Control Plane |
| Campaign API, authorization, task creation | Control Plane web process |
| Campaign and case persistence | Control Plane |
| Batch orchestration and scoring | Control Plane evaluation worker |
| DeepEval metric implementation | reusable core extracted from `fred-deepeval-cli` |
| Browser pages and result visualization | Fred frontend |
| Optional OTLP export | evaluation worker |
| Vendor routing, credentials, fan-out, redaction | customer or platform OTel Collector |

### 7.2 Deployment boundary

The evaluation worker is a separate process and production image. It may share the Control Plane source tree, database models, task service, and Temporal namespace, but it must be built with an optional evaluation dependency group that is absent from the Control Plane web image.

The worker image may install:

- `fred-deepeval-cli[eval]` or its successor reusable package;
- DeepEval and LiteLLM;
- Temporal worker dependencies when Temporal is enabled;
- OpenTelemetry SDK/exporter dependencies when OTLP is enabled.

The following packages remain free of these dependencies:

- `fred-sdk`, except lightweight typed contracts;
- `fred-core`, except generic task models;
- `fred-runtime`;
- Control Plane web image;
- frontend.

### 7.3 Refactoring the external CLI

The current project remains available as a CLI, but its scoring logic is made callable without parsing CLI arguments or writing to stdout.

Proposed internal layout, without requiring a distribution rename in the MVP:

```text
fred_deepeval_cli/
  core/
    models.py
    evaluator.py
    profiles.py
    structural_checks.py
    scorer.py
    judge_factory.py
  cli/
    main.py
    display.py
  worker_adapter.py
```

Required public entry point:

```python
async def evaluate_case(
    request: EvaluationCaseRequest,
    *,
    execution_client: EvaluationExecutionClient,
    judge: EvaluationJudge,
) -> EvaluationCaseResult:
    ...
```

The CLI calls this API for local use. The evaluation worker calls the same API for platform campaigns. CLI JSON and platform result JSON derive from the same typed model.

---

## 8. Product API

All public routes are Control Plane product routes under the configured base URL, normally `/control-plane/v1`.

### 8.1 Create and start a campaign

```http
POST /control-plane/v1/evaluation-campaigns
```

The endpoint validates authorization, target identity, limits, profile, judge profile, and test cases; persists the campaign; creates an evaluation task; and returns immediately.

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
    "version": "2026-06-09",
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
  "task_id": "task-c3711",
  "state": "pending"
}
```

Response status is `202 Accepted`.

### 8.2 Target contract

The target is a discriminated union:

```python
class ManagedInstanceTarget(BaseModel):
    kind: Literal["managed_instance"]
    agent_instance_id: str

class RuntimeAgentTarget(BaseModel):
    kind: Literal["runtime_agent"]
    runtime_id: str
    agent_id: str
```

The frontend never sends a URL. `runtime_id` must resolve through configured `runtime_catalog_sources`. Managed instances resolve through the existing Control Plane product model and execution-preparation flow.

### 8.3 Query endpoints

```http
GET /control-plane/v1/evaluation-campaigns
    ?scope=user|team
    &team_id=<id>
    &state=<state>
    &target_agent_id=<id>

GET /control-plane/v1/evaluation-campaigns/{campaign_id}

GET /control-plane/v1/evaluation-campaigns/{campaign_id}/cases
    ?status=<status>
    &verdict=<verdict>
    &tag=<tag>
    &offset=<n>
    &limit=<n>

GET /control-plane/v1/evaluation-campaigns/{campaign_id}/cases/{case_id}
```

Task progress and cancellation reuse the generic task endpoints:

```http
GET  /control-plane/v1/tasks/{task_id}/events
POST /control-plane/v1/tasks/{task_id}/cancel
```

Campaign deletion, rerun, baseline comparison, CSV export, and scheduled execution are deferred until the MVP contract is proven.

### 8.4 Authorization

No new OpenFGA relation is introduced in the MVP.

| Operation | Required permission |
| --- | --- |
| List/read team campaigns and case results | `TeamPermission.CAN_READ` |
| Create a campaign for a team | `TeamPermission.CAN_UPDATE_AGENTS` |
| Cancel a running campaign | creator, platform owner, or `CAN_UPDATE_AGENTS` on the campaign team |
| Read personal campaign | campaign creator |

The task-event access rule must be amended so a team-scoped task is readable by authorized team members, not only its creator or a platform owner.

---

## 9. Canonical data model

### 9.1 Campaign

```python
class EvaluationCampaign(BaseModel):
    schema_version: Literal["1"] = "1"
    campaign_id: str
    task_id: str
    name: str
    team_id: str
    created_by: str
    target: EvaluationTarget
    dataset_name: str
    dataset_version: str | None
    profile: str
    judge_profile_id: str
    operational_state: TaskState
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

### 9.2 Case result

```python
class EvaluationCaseResult(BaseModel):
    schema_version: Literal["1"] = "1"
    case_id: str
    campaign_id: str
    external_id: str | None
    status: Literal["pending", "running", "completed", "error", "cancelled"]
    outcome: Literal[
        "success", "execution_error", "degraded", "hitl_blocked", "unknown"
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

### 9.3 Metric result

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

Skipped metrics and scorer errors are persisted explicitly. They must not disappear from aggregate calculations.

### 9.4 State semantics

The system exposes independent dimensions:

| Dimension | Meaning |
| --- | --- |
| Task state | Did campaign orchestration run, fail operationally, or get cancelled? |
| Case status | Was this individual case processed? |
| Agent outcome | Did the runtime return success, execution error, degraded output, or HITL block? |
| Metric verdict | Did one metric pass its threshold, fail, skip, or error? |
| Campaign verdict | Did the configured quality policy pass? |

A campaign task reaches `succeeded` when all processable cases have durable terminal records and aggregates were computed. It may still have `verdict="failed"` because the evaluated agent failed quality thresholds.

---

## 10. Task event extension

Amend `TASK-EVENT-STREAM-RFC.md` and `fred_core.tasks.models` with an evaluation variant.

```python
class EvaluationDetail(BaseModel):
    campaign_id: str
    completed: int
    total: int
    passed: int
    failed: int
    execution_errors: int
    scoring_errors: int

class EvaluationTaskEvent(_TaskEventBase):
    kind: Literal["evaluation"] = "evaluation"
    detail: EvaluationDetail | None = None
```

The event target is:

```json
{
  "type": "evaluation_campaign",
  "id": "eval-cmp-8d923",
  "label": "Aegis regression — June 2026"
}
```

The event log contains progress and compact counters only. Inputs, outputs, expected answers, retrieval context, metric explanations, and raw traces are never copied into task events.

---

## 11. Evaluation worker behavior

### 11.1 Workflow

```text
load and lock campaign
resolve target and policy
create one fresh session per case
run cases with bounded concurrency
  ├─ obtain short-lived execution authorization
  ├─ call POST /agents/evaluate
  ├─ classify outcome
  ├─ run structural checks
  ├─ run configured metrics
  ├─ persist case result atomically
  ├─ emit evaluation task progress
  └─ emit optional OTLP trace
compute campaign aggregates and verdict
persist terminal campaign state
emit terminal task event
```

### 11.2 Idempotency

- Each case has a stable internal `case_id` and attempt number.
- A completed attempt is not executed again after worker restart.
- Result persistence uses an idempotency key `(campaign_id, case_id, attempt)`.
- Campaign aggregate calculation is repeatable from persisted case records.
- Worker retries execution and scoring separately so a judge outage does not automatically re-execute an agent tool path.

### 11.3 Concurrency and limits

Server configuration defines hard maxima. A request may choose lower values but cannot exceed them.

Recommended initial defaults:

| Limit | Default | Hard maximum |
| --- | ---: | ---: |
| Cases per campaign | 50 | 200 |
| Concurrent cases | 3 | 10 |
| Agent execution timeout | 600 s | 900 s |
| Judge timeout per metric | 120 s | 300 s |
| Input size per case | 32 KiB | 64 KiB |
| Expected-output size | 32 KiB | 64 KiB |

### 11.4 Temporal

Temporal is the recommended production scheduler for evaluation. The current CLI prototype is not accepted as-is because it uses a fixed workflow ID, serial execution, and carries access tokens in activity parameters.

The production workflow must:

- use a unique workflow ID derived from `campaign_id`;
- use bounded parallel case activities;
- persist results after every case;
- support cooperative cancellation;
- keep user access tokens and judge secrets out of workflow history;
- obtain short-lived credentials inside activities;
- use separate retry policies for runtime calls, judge calls, and persistence.

A local memory runner may be retained for tests and developer mode when the evaluation extra is installed.

---

## 12. Frontend

### 12.1 Routes

```text
/monitoring/evaluations
/monitoring/evaluations/new
/monitoring/evaluations/:campaignId
```

These routes align with the existing monitoring and processor-benchmark navigation.

### 12.2 Campaign creation

The creation page has three steps:

1. **Target** — team, managed agent instance or runtime agent, and supported execution options.
2. **Dataset** — manual rows, JSON upload, or CSV upload; client-side schema validation before submission.
3. **Evaluation policy** — profile, judge profile, metrics/thresholds where permitted, concurrency below the server maximum.

The frontend retrieves targets and judge-profile summaries from server APIs. It never receives judge secrets or runtime service credentials.

### 12.3 Campaign list

Display:

- name;
- target agent and runtime;
- dataset name/version;
- operational state;
- verdict;
- progress;
- pass rate;
- creator;
- creation and completion times.

### 12.4 Campaign detail

Display:

- task progress from the shared task SSE manager;
- campaign verdict and aggregate metric cards;
- case table with filters for status, verdict, outcome, and tags;
- case detail drawer showing input, expected output, actual output, structural checks, metric scores/reasons, latency, tokens, execution errors, and scoring errors;
- raw trace details only when the user is authorized and trace retention is enabled.

The implementation should reuse the interaction patterns of `ProcessorBench.tsx`, `ProcessorRunDetail.tsx`, and `rework/features/tasks`, but not reuse the Knowledge Flow development-only benchmark API.

### 12.5 Generated API types

All request and response types come from Control Plane OpenAPI generation. Hand-written duplicates of evaluation API types are not accepted.

---

## 13. OpenTelemetry export

### 13.1 Decision

OTel is recommended as the vendor-neutral export boundary for customer integrations, but it is not the canonical result format and not a prerequisite for the frontend.

The worker emits one trace per test case. Campaign identity is carried as attributes so vendor backends can group cases.

Suggested root span:

```text
fred.evaluation.case
```

Suggested attributes:

```text
fred.evaluation.schema.version
fred.evaluation.campaign.id
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

Agent execution, structural checks, and scorer calls may be child spans. Metric results may be emitted as evaluation events or metric child spans using current GenAI semantic conventions where compatible, with `fred.*` attributes for fields not covered by a stable standard.

### 13.2 Collector boundary

Production export path:

```text
Evaluation worker → OTLP/HTTP → OpenTelemetry Collector → configured customer exporters
```

The collector owns:

- vendor credentials;
- fan-out;
- batching and retry;
- attribute enrichment;
- customer-specific routing;
- content redaction;
- destination changes.

The frontend and campaign API are vendor-neutral. They do not contain MLflow- or Langfuse-specific fields.

### 13.3 Content policy

Default telemetry behavior:

| Data | Default |
| --- | --- |
| Campaign/case identifiers | enabled |
| Agent/runtime identifiers | enabled |
| Verdicts and numeric scores | enabled |
| Latency and token counts | enabled |
| Metric explanations | disabled |
| User input | disabled |
| Expected output | disabled |
| Actual output | disabled |
| Retrieval context | disabled |
| Raw trace | disabled |
| User identifier | disabled or irreversibly pseudonymized |

Configuration can enable content export only after a deployment owner accepts the privacy and data-residency impact.

### 13.4 Vendor-native adapters

Direct `MLflowExporter` or `LangfuseExporter` implementations are deferred. They may be proposed later if OTLP cannot represent a required first-class vendor object such as an experiment run, dataset item, or score attachment.

Any direct adapter must implement a generic exporter interface and remain an optional worker dependency. It must not change the canonical Fred result schema.

### 13.5 Relationship to platform observability

This RFC does not amend the current platform tracer backend list and does not implement general OTLP push for agent runtimes. Evaluation-worker OTLP is isolated to EVAL-01. A later platform-wide OTLP capability requires a separate `OBSERV` task and RFC amendment.

---

## 14. Persistence and retention

### 14.1 PostgreSQL

Persist searchable operational and quality data in Control Plane storage:

```text
evaluation_campaign
evaluation_case
evaluation_metric_result
```

The campaign row stores aggregate counters and verdict. Case and metric rows permit pagination and filtering without loading full raw traces.

### 14.2 Raw traces

Raw `EvalTrace` payloads can be large and may contain sensitive retrieved content.

Production recommendation:

- store raw traces in configured object storage;
- store only the object reference and content hash in PostgreSQL;
- apply an independent retention period;
- allow trace retention to be disabled by policy.

Local development may use a bounded JSON/JSONB fallback. Payloads exceeding the configured limit are not persisted and the result records `raw_trace_ref=null` with a retention reason.

### 14.3 Retention

Recommended initial defaults:

- campaign summaries and metric rows: 180 days;
- raw traces: 30 days;
- failed export-delivery diagnostics: 14 days.

Deployment owners may override these values. Deletion must remove or expire both relational rows and raw trace objects.

---

## 15. Security and safety

### 15.1 No arbitrary URLs

The API accepts only managed instances or runtime IDs from the configured catalog. This prevents SSRF and ungoverned calls to customer-supplied endpoints.

### 15.2 Credentials

- Judge credentials are referenced by `judge_profile_id` and resolved server-side.
- Runtime credentials are resolved server-side.
- End-user bearer tokens are not persisted in campaign rows, task events, object storage, or Temporal histories.
- The worker uses a dedicated service identity and short-lived execution authorization.
- OTel headers and vendor credentials are deployment secrets, never campaign fields.

### 15.3 Side effects

`POST /agents/evaluate` executes the real agent path. An agent may call tools that mutate external systems.

Therefore:

- evaluation is disabled by default at deployment level;
- production evaluation is allowed only for targets explicitly marked evaluation-safe or bound to an approved evaluation environment;
- side-effecting tool profiles are rejected unless a platform owner enables an explicit override;
- every evaluation case uses a fresh session ID unless a future multi-turn dataset contract is approved;
- the UI displays the target environment and a side-effect warning before start.

A future dry-run or tool-sandbox contract is outside this RFC.

### 15.4 Audit

Audit records include:

- campaign creation and cancellation;
- actor, team, target runtime, and target agent;
- judge profile ID, but not credentials;
- configured case count and concurrency;
- terminal operational state and verdict;
- trace-export policy used for the run.

### 15.5 Cost controls

The server enforces campaign and concurrency limits. Judge profiles may define token or cost budgets. Budget exhaustion produces explicit scoring errors and an `inconclusive` verdict unless the campaign policy specifies otherwise.

---

## 16. Configuration

Configuration is owned by the Control Plane evaluation worker, not `fred-runtime`.

Illustrative shape:

```yaml
evaluation:
  enabled: false
  scheduler_backend: temporal
  max_cases_per_campaign: 200
  max_concurrency: 10
  default_concurrency: 3
  case_timeout_seconds: 600
  judge_timeout_seconds: 120
  raw_trace_retention_days: 30
  result_retention_days: 180
  allow_production_targets: false

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

Secrets are referenced by environment or secret-store keys. They are never returned by the configuration or campaign APIs.

---

## 17. Alternatives considered

### A. Execute the CLI in the browser

Rejected. A browser cannot safely execute the Python CLI, protect credentials, or maintain durable background work.

### B. Spawn `fred-deepeval-cli` as a subprocess in a synchronous API request

Rejected. Subprocess JSON parsing is an unstable internal protocol; request timeouts, cancellation, partial persistence, retries, and horizontal scaling are poor. The CLI must expose a callable core instead.

### C. Frontend calls a standalone evaluation service directly

Rejected for the primary Fred UI. It would duplicate OIDC/ReBAC integration, runtime-catalog resolution, managed-instance execution preparation, and task visibility. The Control Plane is the product boundary.

### D. Install DeepEval in `fred-runtime`

Rejected. It violates the published runtime dependency policy and couples every agent pod to a scoring stack.

### E. Run DeepEval in the Control Plane web process

Rejected. Judge latency and heavy dependencies would affect product API availability and web-worker scaling. Scoring runs in a separate worker image.

### F. Store only OTel traces and query MLflow or Langfuse for the frontend

Rejected. Telemetry backends are optional, vendor-specific, retention-dependent, and not transactional campaign stores. They cannot be the source of truth for authorization, skipped metrics, cancellation, or partial campaign state.

### G. Build direct MLflow and Langfuse integrations first

Rejected. This creates vendor lock-in and duplicated exporters. OTLP through a Collector is the first interoperability layer; native adapters require a demonstrated gap.

### H. Extend platform-wide runtime tracing with OTLP in the same change

Rejected. The repository explicitly defers global OTLP support. Combining platform observability and evaluation productization would expand scope and ownership unnecessarily.

### I. Keep Promptfoo as the primary batch architecture

Not selected for the Fred UI. Promptfoo remains a valid external CI consumer, but the platform needs durable team-scoped campaigns, partial results, task events, and Control Plane authorization. The scorer core remains replaceable so Promptfoo or Inspect AI can coexist outside the product API.

---

## 18. Impact on existing contracts

### 18.1 Runtime execution contract

Amend `docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md` to freeze:

- `POST /agents/evaluate` as the synchronous evaluation execution surface;
- `EvalTrace` and `EvalStep` field semantics;
- equivalence requirements between `/agents/evaluate` and the normal execution path for authentication, execution grants, runtime context, history behavior, and identity propagation;
- the rule that scoring does not run inside `fred-runtime`.

No new runtime endpoint is required by this RFC.

### 18.2 Control Plane product contract

Amend `docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md` with:

- evaluation campaign and case models;
- campaign create/list/detail/case endpoints;
- team authorization rules;
- target resolution rules;
- worker and persistence ownership;
- API status and error behavior.

### 18.3 Task event RFC

Amend `docs/swift/rfc/TASK-EVENT-STREAM-RFC.md` with:

- `EvaluationTaskEvent` and `EvaluationDetail`;
- team-scoped read access for task streams;
- cancellation authorization for evaluation tasks;
- `evaluation_campaign` target type.

### 18.4 OpenAPI

Regenerate Control Plane OpenAPI and frontend generated clients. Evaluation request and result models must not be hand-written in TypeScript.

### 18.5 External CLI contract

The CLI keeps machine-readable JSON on stdout and human rendering on stderr. Its JSON result model is versioned and aligned with the platform `EvaluationCaseResult` model. The CLI remains independently usable without a Control Plane campaign.

---

## 19. Implementation sequence

### Phase 0 — Contract convergence

1. Replace the current v1 RFC with this approved v2 text.
2. Amend the EVAL-01 backlog with platform API, worker, frontend, and OTLP phases.
3. Freeze `/agents/evaluate` and `EvalTrace` in the runtime execution contract.
4. Add the evaluation product surface to the Control Plane contract.
5. Amend the task event RFC.
6. Correct EVAL-01 tracking divergence described in §23.

### Phase 1 — Reusable evaluator core

1. Extract typed request/result models from CLI dictionaries.
2. Extract a callable single-case evaluation service.
3. Make judge selection provider-agnostic and profile-driven.
4. Separate execution, structural-check, metric, and scorer-error results.
5. Add stable schema versions and unit tests.
6. Keep the existing CLI as a thin adapter.

### Phase 2 — Control Plane campaign resource

1. Add campaign, case, and metric persistence.
2. Add create/list/detail/case APIs and authorization.
3. Add runtime/managed-instance target resolution.
4. Add configuration and judge-profile summaries.
5. Add hard request and concurrency limits.

### Phase 3 — Evaluation task and worker

1. Add `EvaluationTaskEvent`.
2. Add campaign workflow and activities.
3. Add bounded parallel execution and per-case persistence.
4. Add cancellation and independent retry policies.
5. Add aggregate calculation and verdict policy.
6. Build the separate worker image with evaluation extras.

### Phase 4 — Frontend

1. Add evaluation campaign list, creation, and detail routes.
2. Add manual, JSON, and CSV dataset input.
3. Integrate shared task SSE and rehydration.
4. Add paginated result table and case detail view.
5. Add permission-aware controls and safety warnings.

### Phase 5 — OTLP export

1. Add optional worker-local OTel SDK/exporter configuration.
2. Emit one trace per case with correlation IDs.
3. Add content-redaction defaults.
4. Validate export through an OTel Collector to at least one supported downstream backend.
5. Persist telemetry trace IDs for correlation.

### Phase 6 — Adoption and hardening

1. Validate a RAG agent, SQL/tool agent, and workflow/HITL agent.
2. Validate no-security and Keycloak-enabled environments.
3. Document dataset authoring and failure diagnosis.
4. Define baseline comparison in a follow-on proposal after campaign storage is proven.

---

## 20. Expected implementation touch points

### Fred repository

- `apps/control-plane-backend/control_plane_backend/evaluations/`
  - `api.py`
  - `models.py`
  - `service.py`
  - `store.py`
  - `worker.py`
  - `workflow.py`
- Control Plane application container, router registration, configuration, and database migrations
- `libs/fred-core/fred_core/tasks/models.py`
- task authorization helpers and tests
- `apps/frontend/src/common/router.tsx`
- new evaluation pages/components under the frontend monitoring surface
- `apps/frontend/src/rework/features/tasks/taskKinds.ts`
- generated Control Plane OpenAPI client
- i18n message files
- runtime and product contract docs
- EVAL-01 backlog, id legend, track/PMO/status convergence files

### `fred-deepeval-cli` repository

- reusable typed core and judge factory
- stable result schema
- worker adapter
- CLI adapter and output compatibility
- unit tests for profiles, structural checks, scorer failures, and serialization

Exact file names may be adjusted during implementation, but responsibility boundaries in this RFC are normative.

---

## 21. Verification plan

### Contract tests

- `/agents/evaluate` still matches the frozen `EvalTrace` schema.
- Control Plane OpenAPI generates discriminated target and task-event unions.
- CLI and platform case-result JSON conform to the same schema version.

### Control Plane tests

- create campaign authorization for personal and team scopes;
- reject unknown runtime IDs and arbitrary URLs;
- reject unauthorized managed instances;
- enforce case-count, size, timeout, and concurrency limits;
- persist partial results and recompute aggregates idempotently;
- distinguish operational state from quality verdict;
- team-authorized task SSE access and cancellation;
- redact secrets from API models, task events, and logs.

### Worker tests

- success, execution error, degraded, and HITL-blocked outcomes;
- structural checks for RAG, SQL, workflow, and default profiles;
- one metric failure does not erase successful metrics;
- judge failure does not re-execute a completed agent call;
- worker restart resumes unfinished cases;
- cancellation stops new case scheduling;
- unique session and workflow IDs;
- no bearer tokens in serialized workflow input/history.

### Frontend tests

- dataset validation and error display;
- create request uses generated API types;
- progress reconnect and task rehydration;
- result filters and case detail rendering;
- permission-aware create/cancel controls;
- raw trace content hidden when retention or authorization disallows it.

### OTel tests

- in-memory exporter receives one root trace per case;
- campaign/case correlation attributes are present;
- content attributes are absent by default;
- export failure does not fail or roll back canonical campaign persistence;
- telemetry trace ID is persisted when export succeeds.

### Live validation

- one `fred-agents` target;
- one external `dt-agents` target;
- one Keycloak-enabled run;
- one cancellation test;
- one Collector export test;
- one side-effect-policy rejection test.

All touched project roots must pass `make code-quality` and `make test`. OpenAPI generation must be clean.

---

## 22. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Judge cost or rate limits | server limits, bounded concurrency, judge profiles, explicit scoring errors |
| Agent tools mutate external systems | evaluation-safe policy, isolated environment, disabled-by-default feature |
| Large traces or sensitive context | object storage, retention limits, content export disabled by default |
| Browser disconnect | persisted task events and case results; SSE replay |
| Worker crash | idempotent case attempts and durable partial persistence |
| Vendor lock-in | canonical Fred result model plus OTLP Collector boundary |
| Heavy dependency impact | separate worker image; no scorer deps in runtime or web image |
| Task success confused with evaluation pass | independent operational state and quality verdict |
| Runtime saturation | per-campaign and global worker concurrency limits |
| Duplicate architecture | explicit amendments to existing contracts and EVAL-01 backlog |

---

## 23. Required repository convergence in the approval change

The repository currently contains tracking divergence for EVAL-01. The approval change should correct it without changing ownership unless the PMO owner confirms:

1. `docs/swift/data/id-legend.yaml`
   - add the missing backlog reference to `docs/swift/backlog/AGENT-EVALUATION-BACKLOG.md`;
   - change status from `not_started` to `in_progress`, because `/agents/evaluate`, `EvalTrace`, and the CLI prototype already exist.
2. `docs/swift/tracks/README.md`
   - change EVAL-01 from “Not started” to “In progress”.
3. `docs/swift/WORKPLAN.md`
   - correct the RFC path from `docs/rfc/...` to `docs/swift/rfc/...`;
   - update the current state to reflect shipped trace and CLI foundations.
4. `docs/swift/PMO-BOARD.md`
   - add the EVAL backlog link in the currently empty backlog column;
   - retain the current owner/status unless explicitly changed by PMO.
5. `docs/swift/STATUS.md` and `docs/swift/data/sprint.yaml`
   - verify status and owner consistency with the canonical ID registry and PMO board.
6. `docs/swift/backlog/AGENT-EVALUATION-BACKLOG.md`
   - add implementation phases for Control Plane campaigns, task events, frontend, persistence, security, and OTLP export;
   - close or rewrite questions already resolved by this RFC.

The RFC path remains `docs/swift/rfc/AGENT-EVALUATION-RFC.md`; this is an amendment/replacement, not a parallel RFC file.

---

## 24. Resolved decisions

| Decision | Approved direction proposed by v2 |
| --- | --- |
| Runtime execution surface | Existing `POST /agents/evaluate` |
| Evaluation unit | Typed `EvalTrace` |
| Browser integration boundary | Control Plane product API |
| Long-running execution | Existing task framework plus separate evaluation worker |
| Scoring implementation | Reusable external evaluator core; DeepEval first |
| Heavy dependency placement | Evaluation worker only |
| Canonical result storage | Fred Control Plane persistence |
| Telemetry role | Optional correlated export, not source of truth |
| Vendor integration | OTLP Collector first; native adapters deferred |
| Runtime target selection | Catalog/managed-instance IDs only; no frontend URL |
| Authorization | Existing team permissions; no new ReBAC relation in MVP |
| Side-effect policy | Deny by default unless explicitly evaluation-safe |
| CLI | Retained as thin local adapter to the same core |
| Promptfoo / Inspect AI | Optional external tools, not Fred UI architecture |

---

## 25. Approval outcome

Approval means the team accepts the architectural boundaries and authorizes preparation of:

- the EVAL-01 backlog amendment;
- the three contract amendments;
- the tracking convergence corrections;
- an execution GitHub issue linking this RFC, EVAL-01, and the backlog;
- a phased implementation plan and branch.

Implementation must not begin until the developer confirmation and execution issue required by `CLAUDE.md` exist.