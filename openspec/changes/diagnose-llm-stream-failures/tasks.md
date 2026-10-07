## 1. Confirm scope and establish fault fixtures

- [x] 1.1 Obtain confirmation of proposal/design/specs, create or reuse the tracking issue and dedicated branch in this checkout; verify the branch base against the selected swift reference and link the issue in proposal.md.
- [ ] 1.2 Turn the loopback HTTP proof into offline fixtures for valid completion, no first chunk, stall after progress and incomplete chunked body using the installed ChatOpenAI stack; verify actual exception types and structured timeout attributes with short deterministic deadlines and bounded server cleanup.

## 2. Instrument the existing model boundary

- [ ] 2.1 Add isolated call-local progress collection and root/child attribution through the existing ReAct/Deep middleware assembly; verify native callbacks remain composed, two interleaved child calls do not contaminate each other, and streaming/tool/reasoning output is unchanged.
- [ ] 2.2 Add exactly-once terminal diagnostics and bounded exception classification, including original cancellation propagation; verify all fault fixtures and cancellation-before-first/after-progress cases produce the correct category/stage and release active-call state.
- [ ] 2.3 Preserve bounded failed-call snapshots through support-error reporting, explicit causes and exception groups; verify a real native Deep child failure can be followed from its support reference to the correct call, with bounded traversal and truncation markers.
- [ ] 2.4 Emit safe effective model/transport settings and dependency versions and capture allow-listed upstream response metadata using call-local response hooks; verify shared clients are reused, overrides/ignored tuning are represented accurately, missing metadata is tolerated and response bodies are never consumed by hooks.

## 3. Expose useful operator signals

- [ ] 3.1 Add bounded call outcome/progress/active-call KPIs through the existing writer and explicit label allow-list; verify first-success-before-error label stability, long-duration buckets, missing-versus-zero semantics, active-count restoration and existing latency compatibility in Prometheus export tests.
- [ ] 3.2 Extend the existing Grafana runtime dashboard with category/role/model error rate, first-chunk/gap/silence distributions, active calls and existing loop-lag/process signals; validate JSON and every query against exported fixture metrics, including service filters and empty-data states.
- [ ] 3.3 Update the existing observability and model-configuration guides with metric semantics, coverage limits, effective timeout layers and support-reference/upstream-ID investigation queries; add the required English migration note and verify that no document promises root-cause attribution or changed retry/timeout behavior.

## 4. Validate and review

- [ ] 4.1 Exercise privacy sentinels with tracing disabled/content capture off and both delegation settings, telemetry sink failures, existing 429 retries and many synthetic chunks; verify no secrets/content/IDs reach forbidden channels, no per-chunk I/O or content retention, and original results/errors are preserved.
- [ ] 4.2 Run focused offline runtime/core tests and root `make code-quality` near completion; record exact outcomes here. Compare collector overhead and output volume with the uninstrumented baseline using the same synthetic stream, and perform the required performance review.
- [ ] 4.3 Apply audit-branch against the actual target and obtain an independent read-only review of implementation with requirements and diff; record base/head, covered consumers, findings/dispositions and exclusions in the PR or task response.
- [ ] 4.4 Reconcile specs with verified behavior, sync/archive using the repository procedure and publish the reviewed draft PR; record that real integration/production attribution still requires deployed evidence unless it has actually been obtained.
