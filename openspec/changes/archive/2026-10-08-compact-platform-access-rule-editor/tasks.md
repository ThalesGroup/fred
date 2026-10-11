## 1. Compact editor

- [x] 1.1 Add opt-in counter visibility while preserving TextInput defaults, maxlength and errors; verify focused input tests.
- [x] 1.2 Implement localized compact condition rows, responsive stacking, accessible selection/removal, visible case handling and separated actions; verify real-account desktop/mobile browser journeys without saving access changes.
- [x] 1.3 Replay and extend editor regressions for draft/preview, case/path editing, combination/removal and counters/errors; verify the focused suite.

- [x] 1.4 Add allow/block mode to the shared policy and editor, preserving default allow, independent exceptions and fresh delegated evidence; test preview, persistence, actor safeguards, missing claims and timeouts.

## 2. Delivery

- [x] 2.1 Obtain bounded independent read-only review, resolve supported findings and run root quality; record reviewed base/head, coverage and limitations.
- [x] 2.2 Reconcile UX/spec artifacts, synchronize and archive; verify strict OpenSpec validation and diff integrity.
- [x] 2.3 Commit/push the approved refinement and add sanitized real screenshots/scenarios to the existing PR; verify implementation CI and conflict-free mergeability. Track final post-closeout readiness in the PR.

Verification: implementation head `4983ffc1d` integrates Swift `05a773919`; root quality passed after the merge. Full and focused independent read-only reviews were completed and supported findings resolved. Exact test counts, real-account browser scenarios, review coverage and exclusions are recorded in PR #2966.

Implementation CI: all 140 checks passed on `4983ffc1d`. Two later asynchronous-test annotations are corrected separately in `ff974b29d`, with Ruff and both affected tests passing, including PostgreSQL. Final pushed-head checks and review-thread disposition remain in PR #2966.
