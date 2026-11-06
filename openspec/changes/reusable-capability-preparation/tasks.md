# Tasks

## 1. Shared contract and persistence

- [ ] 1.1 Add an optional preparation declaration, `prepare` hook and bounded context/result types to fred-sdk; verify contract tests keep existing capabilities valid and reject invalid declarations.
- [ ] 1.2 Add generic asset and preparation tables with owner/revision constraints, indexes and one migration for the PR; verify migration upgrade/downgrade and duplicate/stale revision constraints against PostgreSQL.
- [ ] 1.3 Extend control-plane save validation to admit declared assets, persist immutable originals and a preparation intention atomically with the agent revision; verify authorized/unauthorized, oversized, unchanged and failed-upload cases with focused API tests.
- [ ] 1.4 Add generic status, retry and scoped worker input/result APIs; verify permissions, bounded responses and cross-team isolation with API tests and an endpoint contract description.

## 2. Durable dispatch, worker and readiness

- [ ] 2.1 Add a bounded dispatcher with deterministic Temporal workflow IDs, delivery reconciliation, retry and deadline handling; verify crash and uncertain-delivery cases with focused tests.
- [ ] 2.2 Add a separate `fred-agents` preparation-worker mode and deployment that loads the installed registry and calls the declared hook; verify a worker restart resumes a job without a serving pod or remembered in-process object.
- [ ] 2.3 Derive agent readiness from every current gating preparation plus existing suspension/enabled rules in listings, picker and turn admission; verify two capabilities preparing concurrently, one failure, and a separate suspension.
- [ ] 2.4 Add fenced result publication and idempotent cleanup for superseded/deleted resources; verify replacement, deletion, duplicate completion and late callback races.
- [ ] 2.5 Exercise the public contract with a minimal second test capability through the same save, dispatch, status and readiness path; verify no capability-ID-specific control-plane branch is needed and document the extension points.

## 3. Knowledge Flow vision service

- [ ] 3.1 Add an authenticated internal image-plus-prompt endpoint and model-availability read backed by Knowledge Flow's configured `vision_model`; verify only the worker service can call it and no caller can select a model or pass an arbitrary URL.
- [ ] 3.2 Bound image/prompt size, timeout, concurrency and logs, and reuse the configured model client; verify oversized input, missing configuration, timeout and concurrent-call behavior with focused tests.
- [ ] 3.3 Add the capability-facing vision client and deployment wiring between worker and Knowledge Flow; verify a worker reaches the endpoint with workload identity and a service outage returns a safe error.

## 4. PPT Builder migration to the shared lifecycle

- [ ] 4.1 Declare PPT template preparation in its manifest and move analysis, preview generation and inventory persistence behind its `prepare` hook; verify the agent tool reads the inventory tied to its active template revision.
- [ ] 4.2 Keep the numbered-slot prompt, response validation and heuristic fallback in PPT Builder while calling Knowledge Flow for vision; verify rule-only, valid, malformed and temporarily failed vision responses.
- [ ] 4.3 Move agent template upload, copy, override, retry and status flows to generic assets/preparations; verify team permissions, copied-agent behavior, retry without a new upload and stale-result fencing.
- [ ] 4.4 Move Swift's platform-wide default and candidate replacement to the shared lifecycle while preserving the built-in deck, active-default continuity, reviews, reset and propagation bound; verify admin permissions and failed replacement behavior.

## 5. Settings and model catalog cleanup

- [ ] 5.1 Remove PPT labelling-model inputs and selectors in the agent and platform forms; keep `use_vision` and drive its availability from Knowledge Flow; verify both form layouts and legacy saved selections.
- [ ] 5.2 Remove `supports_vision` and derived vision-profile projections from catalog YAML, SDK/runtime/control-plane schemas, APIs and generated frontend types; verify catalog/routing contract tests and legacy YAML tolerance.
- [ ] 5.3 Update user-facing help and operator configuration guidance for the single Knowledge Flow vision model and generic preparation worker; verify documented settings and deployment values match the actual configuration.

## 6. Data cutover and integration

- [ ] 6.1 Backfill old PPT SQL blobs and successful inventories into immutable assets and results, preserving overrides, active platform default and `use_vision`; verify row/hash/count reconciliation and no re-upload for existing agents.
- [ ] 6.2 Add a rollout switch and legacy reader for the migration window, fence old jobs at cutover, then remove old background/blob paths after verification; verify forward cutover and rollback on a staging copy with active and failed preparations.
- [ ] 6.3 Run multi-replica and concurrency integration checks for hundreds of saves, two capabilities on one agent, worker/KF outages, stale callbacks and cleanup; verify bounded queues, memory and connection usage under the target load.
- [ ] 6.4 Run the required root quality gate and full branch audit against the actual target branch, obtain independent read-only review for the cross-service contracts, reconcile the specs/tasks with the implementation, and record results in the PR.

## Workflow follow-up

- Sync and archive this OpenSpec change after implementation, verification and review are complete.
