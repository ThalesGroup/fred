## 1. Correct measured Fred hazards

- [x] 1.1 Remove quadratic MinIO/GCS directory scans and retain all listing work in the existing worker; test markers/collisions/prefixes, verify worker execution, and replay the large-list probe.
- [x] 1.2 Reuse LangChain's async-callable detection and context-preserving executor for synchronous authored tools; test loop responsiveness, context, awaitable factories, errors and cancellation without replay.

## 2. Verify the dependency boundary

- [x] 2.1 Independently review the smallest LangChain tool-fragment mitigation; preserve full chunk metadata and final merged arguments, keep the public JSON parser untouched, and document residual cases. Implement only the reviewed narrow integration and verify real streaming consumers.

## 3. Close out locally

- [x] 3.1 Run full offline tests for touched packages, raw type checks and root code quality; record benchmark comparisons, author audit and independent performance/minimality review.
- [x] 3.2 Update existing guides/migration note and reconcile/sync/archive specs; verify scoped local commits and no new remote publication. Keep deferred console/audit backpressure and production attribution explicit.

Verification: full offline package suites passed (fred-core 1,118;
fred-sdk 564 with 3 skips; fred-runtime 1,809 with 11 skips and 21 deselections).
Raw type checks: zero errors; 2 existing core and 7 existing runtime warnings.
Independent read-only review covered swift `9b2b5162` through the hardening code
(including subsequent annotation/private-reference-only edits): no actionable
findings; 2,810 differential chunk cases matched. Parent equivalence and real
HTTP/SDK streaming tests passed. Executor throughput under production load and
live dashboard rendering were not independently revalidated in this slice.

Local synthetic comparisons: the 10,000-file listing fell from roughly 3.6 s
to 28–108 ms; a 250 ms sync handler left about 2 ms measured loop lag; a 20 KB
non-object fragment fell from roughly 609 ms to 0.08 ms. These are single-host
probes with scheduling/GC variability, not production throughput guarantees.
Console backpressure and object-prefixed parser costs remain explicit residuals.

Root `make code-quality` passed across all modules. The final narrow SDK/parser
checks passed after typing/test-only adjustments. `make migration-check` remains
blocked by the pre-existing published-note mutation
`2910-remove-unused-task-tray.md` on swift; this change's note parses successfully.
Specs are reconciled with the final implementation; local-only publication policy
is preserved. Scope: no new retry, timeout, queue or audit loss policy.
