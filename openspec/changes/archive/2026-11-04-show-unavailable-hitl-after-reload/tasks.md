## 1. Runtime availability

- [x] 1.1 Add the optional typed history availability annotation and regenerate affected API clients; verify schema generation and compatibility with omitted fields.
- [x] 1.2 Resolve trailing unanswered occurrences from shared checkpoint and claim state after session ownership checks; verify focused tests for pending, absent, started/consumed, live and expired claims, sibling identities, unknown state and unauthorized reads.
- [x] 1.3 Verify bounded query growth and cross-replica consistency using independent runtime/checkpointer instances; assert that history reads perform no claim mutations or execution.

## 2. Managed chat presentation

- [x] 2.1 Carry availability through history reconstruction, trace status and sidebar state; verify unavailable questions have no answer controls or running/waiting label while genuinely pending siblings remain actionable.
- [x] 2.2 Add localized unavailable and unknown notices with lookup retry; verify readable history, actual tool-result precedence and legacy responses without annotations.
- [x] 2.3 Refresh the same conversation's history after an authoritative obsolete 409; verify session-switch guards, no automatic answer replay and preserved drafts for retryable conflicts.

- [x] 2.4 Restore existing background HITL toasts on admin pages by hosting their subscription above the router; verify the original conversation link and a single notification with unit tests and Playwright. This localized follow-up was requested during implementation; the equivalent upstream correction in `0773ff95d` is retained on integration.

## 3. Validation and delivery

- [x] 3.1 Use Playwright to cover reload with unavailable and pending questions, unknown-state retry and the stale-answer race; retain screenshots or videos showing the rendered states.
- [x] 3.2 Verify a consumed checkpoint with missing response history against the runtime history endpoint, then reload that fixture in the browser; confirm the card cannot be resubmitted without modifying execution or stored history.
- [x] 3.3 Update the relevant runtime/UI contract and migration note; verify the disconnected-turn lifecycle in runtime contract section 8.89 remains unchanged.
- [x] 3.4 Apply the full branch audit and obtain independent read-only review against the actual PR base; resolve findings and record reviewed revisions, evidence and exclusions.
- [x] 3.5 Run root code quality once before committing the completed block, push the scoped change and follow required PR checks to green; reconcile and archive the approved OpenSpec change after verification.


## Verification evidence

- Frontend suite: 393 files passed, one skipped; 4,944 tests passed, eight skipped. Focused runtime/history/checkpoint suite: 84 passed. Core history/schema suite: 15 passed.
- Playwright on the production frontend with controlled HTTP/SSE and notification events: five availability scenarios and the admin-page background HITL toast passed. The admin toast opens its originating conversation. Screenshots/videos are retained in the session artifacts. This does not certify a deployed multi-pod system or Keycloak refresh behavior.
- Independent read-only audit covered the full PR from base `53e39f6f77e63bbc8238b881df38686df5be452e` through `34e2c6afeeb6a314ae95b48c9cacafe3fc2d63aa` plus this working-tree implementation, including authorization, shared claims, occurrence identities, frontend drafts/races, notifications, consumers and documentation. Both findings were fixed and re-reviewed: use admission's checkpoint ordering, and preserve cached session rendering after a lookup retry followed by navigation. No remaining actionable findings. Runtime performance review includes the fixed five-query bound for 100 sibling requests and independent SQL connections; deployed PostgreSQL load testing is excluded.

- Merge review of `58cc406fd` against parents `f10907330` and `0773ff95d` confirmed one App notification subscriber, preserved interrupted-turn suppression and retained HITL reconciliation. The 139 focused frontend tests and admin-page Playwright scenario passed after integration. Root quality passed; GitHub reported 134 successful checks and three conditional skips on `58cc406fd`.
- The user confirmed retaining server-side availability. A subsequent frontend-only correction preserves the rendered trace annotation when opening its detail and aligns its badge and generic payload. Page/detail/trace tests: 270 passed; Playwright reproduced reload plus opening the unavailable question and verified the corrected detail. No execution or runtime lifecycle change was added.
- Independent review of the detail-only delta against `58cc406fd` found no actionable issues; stable selection, live updates, real-result precedence and both localized states were checked. The previous full-PR and merge reviews remain applicable.
