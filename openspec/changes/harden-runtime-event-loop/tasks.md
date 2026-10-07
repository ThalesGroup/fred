## 1. Correct measured Fred hazards

- [ ] 1.1 Remove quadratic MinIO/GCS directory scans and retain all listing work in the existing worker; test markers/collisions/prefixes, verify worker execution, and replay the large-list probe.
- [ ] 1.2 Reuse LangChain's async-callable detection and context-preserving executor for synchronous authored tools; test loop responsiveness, context, awaitable factories, errors and cancellation without replay.

## 2. Verify the dependency boundary

- [ ] 2.1 Independently review the smallest LangChain tool-fragment mitigation; preserve full chunk metadata and final merged arguments, keep the public JSON parser untouched, and document residual cases. Implement only the reviewed narrow integration and verify real streaming consumers.

## 3. Close out locally

- [ ] 3.1 Run full offline tests for touched packages, raw type checks and root code quality; record benchmark comparisons, author audit and independent performance/minimality review.
- [ ] 3.2 Update existing guides/migration note and reconcile/sync/archive specs; verify scoped local commits and no new remote publication. Keep deferred console/audit backpressure and production attribution explicit.
