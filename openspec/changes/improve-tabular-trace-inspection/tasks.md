## 1. Responsive query inspection

- [x] 1.1 Add a synthetic wide-query regression at the actual `TraceDetailDrawer` seam; verify it reproduces excessive rendering with the current code without committing private conversation data.
- [x] 1.2 Bound response/oversized-SQL previews, remove result JSON highlighting and retain complete-original copy actions; verify visible SQL, bounded DOM/highlighter work, truncation notices and copied contents in drawer/code-block tests.
- [x] 1.3 Keep preview derivation stable when unrelated messages stream and when steps switch/reopen; verify selected-call contents and repeat rendering with integration tests and the private replay harness.

## 2. Tabular payload estimates

- [x] 2.1 Add a supported-tool helper deriving approximate argument/result token sizes from recorded parts; verify supported historical/MCP aliases, complete-result counting, pending/missing versus empty output and rejection of unsupported tools with unit tests.
- [x] 2.2 Display localized approximate input/output sizes beside status/duration in the drawer; verify French/English labels, accessible explanations, failed-call compatibility and live/history equivalence in drawer tests.

## 3. Verification and close-out

- [ ] 3.1 Run affected frontend tests and typecheck, then root `make code-quality`; re-run the captured-step replay and verify the live conversation if browser control is available, recording measured improvement and any remaining browser limitation here or in the PR.
- [ ] 3.2 Update `docs/swift/ux/COMPONENT-UX.md`, perform the required author audit and independent read-only review against `origin/swift`, and record base/head, findings, dispositions and exclusions in the PR; verify no billing/context total or backend API changes.
- [ ] 3.3 Reconcile acceptance scenarios and verification evidence, sync/archive the completed OpenSpec change and publish the dedicated branch as a draft PR linked to #3527 and Epic #2738; verify OpenSpec validation and the final PR diff.
