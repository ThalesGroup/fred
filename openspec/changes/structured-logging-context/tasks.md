# Tasks

Apply the agreed source specification and [design](design.md) sequentially. Finish and review each slice before starting the next; one implementation agent retains context. Use focused offline checks locally and broad CI verification, as requested. All PRs remain draft and assigned to `florian-muller`.

## 1. P1 — Shared output foundation

- [x] 1.1 Preserve both local `docs/design` files before branch changes and initialize the output layer with gh-stack rooted on `swift`; verify the saved files and `gh stack view --json` without publishing the local source specification.
- [x] 1.2 Integrate structlog/stdlib processing and producer-task context snapshots in `libs/fred-core/fred_core/logs`, replacing width-sensitive console formatting while preserving the store adapter, structural categories and isolated audit channel; extend the existing `test_log_setup.py` with one real output-contract check covering context, extra, embedded newlines, severity and creation timestamp, and retain existing store/audit checks.
- [x] 1.3 Make repeated setup safe, retain captured warnings and useful dependency warnings/errors without recursive store emission, and preserve sanitized exception behavior; verify repeated initialization and representative readable/redirection output through focused checks without asserting processor arrangements or exact messages.
- [x] 1.4 Add the shared typed `app.log_format` setting and wire Control Plane, Knowledge Flow and hosted agent runtime startup using existing stable identities and API role; regenerate affected backend/Helm schemas and verify reference values explicitly select JSON while omitted local values select text.
- [ ] 1.5 Add an English output migration note under `docs/swift/ops/migrations`, inspect the slice diff, complete applicable independent correctness/performance review, commit and publish its draft PR assigned to the user; verify the PR title includes #2906, attach the PR to this chat, and record focused checks plus broader CI evidence.

## 2. P1 — Request and journey context

- [ ] 2.1 Add the next gh-stack layer and shared ASGI request/completion integration across the three APIs; replace duplicate Knowledge Flow/Uvicorn access events and expose reference headers through CORS. Verify one event at real response/stream termination, safe routes, fresh request IDs, truthful absent status and failed-probe visibility using existing request logging coverage and representative focused checks.
- [ ] 2.2 Bind authenticated/admitted user and resolved team/session/exchange/run/template/instance context at shared conversation, runtime turn and upload/attachment orchestration; align SDK/runtime traceability to ingress references and add tool scopes/outcomes at existing `ToolExecution`. Verify representative normal/resumed chat, ReAct/Deep/Graph tool and upload journeys without a test matrix for every route.
- [ ] 2.3 Implement explicit scope clearing/restoration and safe retained-task ownership, including a request-owned completion snapshot; add one deliberately interleaved request isolation/error-or-cancellation/subsequent-request scenario and verify actual sync/thread and delayed-sink transitions used by Fred.
- [ ] 2.4 Reconcile observability §6/§7, the active delegated-execution neutral-access requirement/scenarios and affected runtime/product contract notes with admitted metadata-only logs; verify existing sensitive-data, audit-isolation and metric-label checks still protect their original boundaries.
- [ ] 2.5 Add the slice migration note, complete independent correctness/performance review, commit and publish the assigned draft PR; attach it and verify focused checks and CI on its current head before advancing.

## 3. P1 — Delegated downstream correlation

- [ ] 3.1 Add the next stack layer and shared versioned bounded context encoding/validation with documented exact byte/type/depth/count limits and reserved fields; verify boundary values and event-extra collision behavior through focused observable checks.
- [ ] 3.2 Attach safe bound context per invocation in existing delegated first-party REST/MCP adapters and accept it only after existing receiver principal/grant admission; extend existing delegation receiver/outbound/MCP tests for inherited fields, authoritative local identities, ordinary user bearer/disabled mode and malformed/oversized input.
- [ ] 3.3 Verify shared-client calls cannot leak context to subsequent calls, external providers, authentication endpoints or untrusted redirects; preserve existing authentication failures and sanitized diagnostics without serializing credentials or event-only extra.
- [ ] 3.4 Document the transport and precedence in the existing observability/delegation guidance, add the migration note, complete independent trusted-propagation/performance review and publish the assigned draft PR; attach it and verify focused checks and CI on the current head.

## 4. P2 — Workers and ingestion

- [ ] 4.1 Add the next stack layer and apply common logging setup/format/service role to active worker entrypoints, starting with Knowledge Flow `main_worker.py` and Control Plane `main_worker.py`; verify representative worker startup output without Temporal or another external service.
- [ ] 4.2 Capture optional bounded safe context before `IngestionDelivery.admit` persists `PipelineDefinition`, carry it through existing scheduler/delivery handoff, and restore scopes around activities with workflow/run/activity/document/task/attempt references; extend an existing ingestion delivery/activity test for durable handoff and retry identity.
- [ ] 4.3 Preserve absent-envelope jobs and fresh scheduled correlations, keeping generation/export out of workflow code and respecting replay-aware logging; verify a legacy payload still executes and deterministic workflow behavior remains compatible using existing focused worker tests.
- [ ] 4.4 Update existing ingestion/observability guidance and the worker migration note, complete independent concurrency/performance review, commit and publish the assigned draft PR; attach it and verify focused checks plus CI, explicitly distinguishing offline verification from rollout verification.

## 5. P3 — Frontend pod

- [ ] 5.1 Add the final stack layer and configure escaped JSON nginx access logs in `apps/frontend/dockerfiles/docker-entrypoint.sh` with event time, status-derived severity and safe metadata; verify rendered configuration and representative output escaping/query omission using existing smoke infrastructure where available, keeping container-dependent checks outside default offline tests.
- [ ] 5.2 Inventory native nginx error/startup output and document collector parsing limits and activation/rollback in existing frontend/observability guidance and an English migration note; verify the note clearly identifies any unverified deployment behavior.
- [ ] 5.3 Review the final slice, commit and publish its assigned draft PR, attach it and verify focused checks plus CI on its current head.

## 6. Stack verification and close-out

- [ ] 6.1 Reconcile all artifacts against implemented behavior and approved scope; verify every task's evidence is recorded here or in its PR, without adding parallel status documents.
- [ ] 6.2 Sync the durable delta and archive the completed change using repository procedures; verify strict spec validation and absence of superseded current logging requirements. Record GKE severity/timestamp/field-filtering canary as a rollout limitation, not a claimed automated/deployment pass.
- [ ] 6.3 Check all five draft PRs against their current bases/heads for required successful CI, no conflicts and no unresolved/actionable review feedback; fix outstanding problems, verify assignment and stack ordering, and update issue #2906 with the complete PR list and honest remaining rollout limitations without merging or converting drafts.

Slice 1 evidence: 45 focused logging/sensitive-data tests passed; changed-file Ruff checks passed; raw basedpyright on the logging modules returned 0 errors/warnings; backend configuration schemas and Helm schema regenerated with existing scripts; chart values validated. uv regenerated consuming locks (Knowledge Flow also normalizes pre-existing platform markers). GKE collector promotion remains unverified.

Slice 1 review corrections: sanitize dependency descendants on a dedicated handler; capture typed producer snapshots through the stdlib record factory; impose aggregate 4KiB/128-node validation budgets plus event-property count bounds; initialize Knowledge Flow output before its model/GPU/container startup events; reuse canonical channel constants and remove obsolete task/marker machinery. Focused regression checks pass (45 total).
