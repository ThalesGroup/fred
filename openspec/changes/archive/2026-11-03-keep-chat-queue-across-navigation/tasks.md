## 1. Implementation

- [x] 1.1 Own pending messages by session in the existing tab registry; retain them on navigation and drain only in the open conversation.
- [x] 1.2 Apply detached steering delivery and clear only the owning queue on interruption, Stop or deletion.

## 2. Verification and close-out

- [x] 2.1 Cover navigation/remount, completion, detached delivery, real cuts, deletion and reattachment without background sends; run focused tests and root quality.
- [x] 2.2 Review the cumulative PR and the new delta independently; reconcile existing docs, sync the spec, archive the change and update the independent PR against swift for issue #3427.

Verification: 276 tests passed across five focused frontend suites after rebasing onto swift. The typed HITL fixture correction also passed its 112-test suite. Root make code-quality passed across all modules with Node 24.22.2. Changed spec, delta and migration declaration validate; global strict spec validation still flags the unrelated pre-existing frontend-surface-scale placeholder Purpose.

Independent read-only review covered base d93037008 and the complete new implementation. Same-commit history/HITL hydration and Stop during another conversation's preflight were found, corrected and covered by regressions; final review left no actionable finding. Browser/provider/load validation excluded. Issue #3427 and independent draft PR #3429 track the work; the base navigation PR #3418 is already merged.
