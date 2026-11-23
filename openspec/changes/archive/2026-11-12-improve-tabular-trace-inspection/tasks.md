## 1. Responsive query inspection

- [x] 1.1 Add a synthetic wide-query regression at the actual `TraceDetailDrawer` seam; verify it reproduces excessive rendering with the current code without committing private conversation data.
- [x] 1.2 Bound response/oversized-SQL previews, remove result JSON highlighting and retain complete-original copy actions; verify visible SQL, bounded DOM/highlighter work, truncation notices and copied contents in drawer/code-block tests.
- [x] 1.3 Keep preview derivation stable when unrelated messages stream and when steps switch/reopen; verify selected-call contents and repeat rendering with integration tests and the private replay harness.

## 2. Tabular payload estimates

- [x] 2.1 Add a supported-tool helper deriving approximate argument/result token sizes from recorded parts; verify supported historical/MCP aliases, complete-result counting, pending/missing versus empty output and rejection of unsupported tools with unit tests.
- [x] 2.2 Display localized approximate input/output sizes beside status/duration in the drawer; verify French/English labels, accessible explanations, failed-call compatibility and live/history equivalence in drawer tests.

## 3. Verification and close-out

- [x] 3.1 Run affected frontend tests and typecheck, then root `make code-quality`; re-run the captured-step replay and verify the live conversation if browser control is available, recording measured improvement and any remaining browser limitation here or in the PR.
- [x] 3.2 Update `docs/swift/ux/COMPONENT-UX.md`, perform the required author audit and independent read-only review against `origin/swift`, and record base/head, findings, dispositions and exclusions in the PR; verify no billing/context total or backend API changes.
- [x] 3.3 Reconcile acceptance scenarios and verification evidence, sync/archive the completed OpenSpec change and publish the dedicated branch as a draft PR linked to #3527 and Epic #2738; verify OpenSpec validation and the final PR diff.

## Verification evidence

- Six affected frontend suites: 288 tests passed. Frontend typecheck, touched-file formatting, `git diff --check`, root `make code-quality` (Node 24.22.2 and existing uv), migration-note validation and all 42 capability specs passed.
- Private captured-step replay: 3.8-4.2 seconds and 19,101 DOM nodes before; 151-164 ms and 257 nodes after, SQL visible. These are happy-dom renderer measurements, not browser paint timings; customer data remains outside the repository.
- Author audit and independent read-only review: target `origin/swift` at `ed1b056fe5830226563717ebfe0012559b6f0989`, merge base `743a0666bfd993a6d442bd50e6f6ae89e18741ce`, implementation head `a0e5b4baf9e89e9e8007fb0606de363d58cb27f5`. No actionable implementation findings; the close-out migration note was added and independently checked. Full coverage and exclusions are recorded in the PR.
- Live conversation validation in the connected Chrome remains unavailable: its browser control fails with `Cannot read properties of undefined (reading 'timeoutMs')`. Screen-reader validation remains unverified. Automated rendering, copy, streaming/history, FR/EN, failure/empty states and compatibility tests passed.
- Follow-up visual comparison used the real components and product styles in the working integrated browser with temporary synthetic fixtures and an `origin/swift` baseline. Desktop, 375 px and 320 px layouts, light/dark themes, long schema titles, SQL/results, keyboard tooltip dismissal and drawer close/reopen passed. Panel width, colors, typography, padding and close-button alignment matched the baseline; small-screen header height grows to fit the added badges. Temporary fixtures were removed without product-code changes.
- Publication: draft PR [#3528](https://github.com/ThalesGroup/fred/pull/3528), targeting `swift`, linked to #3527 and Epic #2738. The final close-out commit contains the synchronized capability requirements, archive move and this evidence only.
