Design: [INGESTION.md](../../../docs/swift/design/INGESTION.md). Keep this change open until remaining checks pass.

## 1. Implemented and observed
- [x] 1.1 Profile extraction queues, role registrations, Helm inheritance/coverage checks and local role commands.
- [x] 1.2 Per-profile admission, document failure containment, execution budgets and child-process supervision (remaining gaps below).
- [x] 1.3 Targeted admission/process tests: 34 passed; these do not prove real extractor recovery.
- [x] 1.4 Local real-stack test: 11 PDFs completed (5 fast, 4 medium, 2 rich), profile routing and common indexing observed; separate profile submissions.
- [x] 1.5 Centralize architecture and developer/operations guidance; remove duplicated audit narrative.

## 2. Remaining before closure
- [ ] 2.1 Resolve unconfirmed-stop worker policy, pull-metadata retry tolerance and total retry-budget expectations.
- [ ] 2.2 Restore child OCR/VLM metrics, extraction/output queue-wait emission and workflow outcomes; resolve Prometheus label filtering before building the queue/stage/profile dashboard.
- [ ] 2.3 Run one mixed-profile submission (rich first); inject one invalid document and verify sibling completion and terminal reconciliation.
- [ ] 2.4 Verify real extraction cancellation at startup, mid-run and repeated during cleanup; expired/exhausted budgets; no overlapping or surviving child/descendant.
- [ ] 2.5 Kill a worker, including a case with a descendant; verify cleanup and recovery after restart.
- [ ] 2.6 Interrupt indexing storage after extraction; verify retry without re-extraction or duplicate chunks.
- [ ] 2.7 Run representative load; measure spawn cost, queue/runtime latency, parent/child CPU/RAM, restarts/OOM; derive Kubernetes sizing.
- [ ] 2.8 Final quality checks, independent review and evidence reconciliation; then sync/archive OpenSpec.
