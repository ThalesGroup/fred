## 1. Implementation and verification

- [x] 1.1 Add explicit portal roots and bidirectional traversal; verify unit coverage for root updates and excluded controls.
- [x] 1.2 Update packed consumer and verify actual Tab/Shift+Tab traversal, nested Dialog and close behavior in browser smoke.
- [x] 1.3 Update migration guidance, run package and root quality gates, reconcile and archive the approved change.

Verification: 139 targeted component tests; isolated packed UI consumer including negative declaration tests; browser smoke with actual forward/reverse portal traversal and nested Dialog navigation; root `UV_NO_SYNC=true make code-quality`; migration-note validation and `git diff --check` passed. Independent local agent review unavailable (agent thread limit); GitHub review requested after push.
