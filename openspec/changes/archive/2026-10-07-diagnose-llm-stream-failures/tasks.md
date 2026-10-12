## 1. Confirm scope and establish fault fixtures

- [x] 1.1 Obtain confirmation of proposal/design/specs, create or reuse the tracking issue and dedicated branch in this checkout; verify the branch base against the selected swift reference and link the issue in proposal.md.
- [x] 1.2 Turn the loopback HTTP proof into offline fixtures for valid completion, no first chunk, stall after progress and incomplete chunked body using the installed ChatOpenAI stack; verify actual exception types and structured timeout attributes with short deterministic deadlines and bounded server cleanup.

## 2. Instrument the existing model boundary

- [x] 2.1 Add isolated call-local progress collection and root/child attribution through the existing ReAct/Deep middleware assembly; verify native callbacks remain composed, two interleaved child calls do not contaminate each other, and streaming/tool/reasoning output is unchanged.
- [x] 2.2 Add exactly-once terminal diagnostics and bounded exception classification, including original cancellation propagation; verify all fault fixtures and cancellation-before-first/after-progress cases produce the correct category/stage and release active-call state.
- [x] 2.3 Preserve bounded failed-call snapshots through support-error reporting, explicit causes and exception groups; verify a real native Deep child failure can be followed from its support reference to the correct call, with bounded traversal and truncation markers.
- [x] 2.4 Emit safe effective model/transport settings and dependency versions and capture allow-listed upstream response metadata using call-local response hooks; verify shared clients are reused, overrides/ignored tuning are represented accurately, missing metadata is tolerated and response bodies are never consumed by hooks.

## 3. Expose useful operator signals

- [x] 3.1 Add bounded call outcome/progress/active-call KPIs through the existing writer and explicit label allow-list; verify first-success-before-error label stability, long-duration buckets, missing-versus-zero semantics, active-count restoration and existing latency compatibility in Prometheus export tests.
- [x] 3.2 Extend the existing Grafana runtime dashboard with category/role/model error rate, first-chunk/gap/silence distributions, active calls and existing loop-lag/process signals; validate JSON and every query against exported fixture metrics, including service filters and empty-data states.
- [x] 3.3 Update the existing observability and model-configuration guides with metric semantics, coverage limits, effective timeout layers and support-reference/upstream-ID investigation queries; add the required English migration note and verify that no document promises root-cause attribution or changed retry/timeout behavior.

## 4. Validate and review

- [x] 4.1 Exercise privacy sentinels with tracing disabled/content capture off and both delegation settings, telemetry sink failures, existing 429 retries and many synthetic chunks; verify no secrets/content/IDs reach forbidden channels, no per-chunk I/O or content retention, and original results/errors are preserved.
- [x] 4.2 Run focused offline runtime/core tests and root `make code-quality` near completion; record exact outcomes here. Compare collector overhead and output volume with the uninstrumented baseline using the same synthetic stream, and perform the required performance review.
- [x] 4.3 Apply audit-branch against the actual target and obtain an independent read-only review of implementation with requirements and diff; record base/head, covered consumers, findings/dispositions and exclusions in the PR or task response.
- [x] 4.4 Reconcile specs with verified behavior and prepare the reviewed publication, including the repository sync/archive lifecycle; record that real integration/production attribution still requires deployed evidence unless it has actually been obtained.

## Verification and review evidence

- Full offline `make test PYTEST_OPTS=-q`: fred-runtime **1,808 passed, 11 skipped, 21 deselected** (one existing Pydantic warning); fred-core **1,112 passed, 42 deselected**. The runtime skips need the optional `fastapi_mcp` package. Fault fixtures permit loopback only; no deployment or provider traffic was used.
- Root `make code-quality`: all checks passed. Raw `basedpyright --baseline-file <absent temporary file>`: runtime **0 errors, 7 existing unreachable-code warnings**; core **0 errors, 2 existing unreachable-code warnings**. No warning or masked error in touched files.
- Prometheus 3.5.0 `promtool test rules`: **18 query assertions passed** across all nine added panels, including selected/empty service fixtures and native process metrics. JSON and `git diff --check` passed.
- Callback microbenchmark, 100,000 callbacks × 5 repeats: baseline 0.053 µs/callback, collector 0.378 µs, incremental **0.324 µs**. State stays at 11 scalar fields, no chunk retention. Synthetic middleware replay at both 100 and 10,000 callbacks: baseline 2 log records + 1 timer; instrumented 4 log records + 4 timing emissions + 1 counter + 2 gauge emissions. No per-chunk output. This is not a production-load benchmark.
- Author audit and independent read-only branch/performance review: target `swift` at `9b2b5162afe1578788f34728a1dc5f4a338cbacc`, planning HEAD `cdaf153e9b4461b4134af6420ec6c3b8b50ec0b6` plus the complete implementation/docs/dashboard working diff (implementation committed as `30c08ae04`). Covered shared HTTP clients/factory, callback composition, concurrent native Deep children, cancellation/error propagation, privacy, KPI export, existing trace/latency consumers and Grafana queries. Findings fixed and independently rechecked: implicit graph streaming classification (P2), tuple/effective client timeouts (P3), and preservation of response model span metadata. Subsequent coroutine-wrapper, loopback-test marker and formatting deltas received author review and full offline tests.
- `make migration-check` has a pre-existing target-branch failure: published `2910-remove-unused-task-tray.md` differs from `code/v3.2.0`. Reproduced with `Repo(head='origin/swift').notes('code/v3.2.0')`; this branch leaves that file untouched. The new impact-none note parses successfully. Do not claim the aggregate migration check passes.
- No live deployment, provider attribution, production load test or Graph/summarization/capability-internal coverage. The two reported exception signatures are reproduced synthetically; the real incident cause still requires deployed logs, gateway settings and provider records. Tracking issue #2988 remains open for that investigation.
