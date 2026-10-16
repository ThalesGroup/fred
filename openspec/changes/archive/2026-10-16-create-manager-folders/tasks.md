## 1. Folder contract and UI

- [x] 1.1 Move creation into governance routes and validate names/depth; verify root/nested creation, role matrix, invalid parents, duplicates, revocation and OpenFGA request budgets in Rust tests.
- [x] 1.2 Reuse the folder dialog and generated manager mutation with live write authorization, pending guard and scoped refresh; verify real RTK UI tests, legacy dialog tests and generated contract.

## 2. Verification and close-out

- [x] 2.0 Add the user-requested exhaustive action/role matrix with scope, inheritance, server prerequisites and explicit Python/Rust semantic differences; independently review it against all manager routes.

- [x] 2.1 Extend the existing browser journey for real personal/team folder creation and errors; run the focused journey and required manager/unit/integration/root-quality checks.
- [x] 2.2 Apply branch audit and independent read-only reviews; fix actionable findings with regression coverage and obtain correction review.
- [x] 2.3 Perform the dedicated arc42 documentation pass, regenerate/check derived blocks, reconcile/validate/sync/archive OpenSpec and commit the single lot locally.

## Review and verification evidence

Scope: folder lot against `c4be0d8623f2ceb4ded81217b350ab02c4e9bb73`, including
untracked dialog and architecture matrix. Actual branch target `origin/swift` at
`3a222ff6c90e02d0db16299548683ff119684b14`, merge base
`e44837560a2b45df2e23802cd8c067097d5cf00d`. Branch inventory covers 236 committed
files (frontend 71, manager 62, OpenSpec changes 59, architecture 16, other docs 11,
Make support 7, deployment 4, capability specs 2 and root files 4). Detailed author
and independent review focuses on the folder journey, affected consumers and
role contracts; this is not approval of the whole historical branch or deployment.

- Backend reviewer checked governance registration, write locking/fencing, parent
  integrity, validation and measured FGA budgets. No code finding; corrected the
  Temporal availability wording to distinguish handler independence from full
  binary startup. No role model change.
- UI reviewer checked generated contracts/retry transport, scoped lifecycle,
  authorization visibility, legacy adapter, modal interaction and styles. Confirmed
  long-parent overflow was fixed with constrained/wrapping header text and a browser
  regression. Independent Chromium correction review verified Close within 390px.
- Final correction reviewer checked Breadcrumb wrapping against real consumers and
  the no-overflow browser assertion, plus documentation corrections against source.
  The explicit self-assignment paragraph was independently checked against grant
  and may_change; it documents existing behavior without changing roles.
- Role reviewer accounted for all 30 HTTP operations and 17 permission values;
  corrected real-authentication/target-identity platform gates, conditional Python
  admin charter activation and read/write sequence labeling. Python differences
  are documented as observed behavior, not collective acceptance of those choices.
- `make test`: 36 unit tests and 5 OpenAPI tests pass.
- `make test-integration`: 73 pass, including names/depth/parent/role matrix,
  concurrent duplicates and the revoked lock waiter.
- `make test-browser`: real OIDC/demo import/personal and team folder creation,
  nested folder, duplicate, mobile long-name and previous browsing assertions pass
  (61.14s); the accompanying 73 integration tests pass (20.63s).
- Focused frontend suite: 26 tests pass across Resources, legacy dialog,
  Breadcrumb, router and generated manager API. TypeScript passes.
- Root `make code-quality` passes across all modules, including frontend TypeScript,
  Prettier and ESLint.
- Manager Clippy, Rustfmt and model consistency pass. Generated client refreshed
  with `make update-fred-manager-api`; DTO output remains unchanged.
- Architecture generated blocks and all Mermaid renders pass after correcting a
  sequence-label semicolon. Migration check passes with existing seven branch notes.
- The first browser attempts failed before the feature on cold Vite graph loading;
  isolated cache plus router warmup removes that fixture instability. A diagnostic
  cache under target was removed after Prettier scanned it; no source lint warning
  is suppressed. Screenshots inspected for conflict and long-parent dialogs.

Tracking: existing issue #3092 remains open for the reconstruction. One local
commit, no push. The team's overall manual review/test is the next user step;
automated checks here cover this lot and its regressions.
