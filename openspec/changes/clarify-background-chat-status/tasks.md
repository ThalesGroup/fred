## 1. Sidebar behavior

- [x] 1.1 Render a readable localized waiting chip and a plain blue completed-unread dot using existing registry state.
- [x] 1.2 Identify successful final SSE completion and preserve queue/HITL behavior on errors, cancellation and navigation.

## 2. Verification and close-out

- [x] 2.1 Test status transitions and localization, inspect real-browser geometry, and run focused suites and root quality.
- [x] 2.2 Independently review, update existing docs/operator guidance and issue/PR scope, then sync and archive the approved change.

Verification: 292 tests passed in six frontend suites; the page suite passed again (49 tests) after removing the Sending icon. Root `make code-quality` passed before the final history-restoration delta; TypeScript, targeted ESLint and Prettier passed on that delta. Real-component browser checks covered EN/FR, light/dark themes, 200/240 px sidebars and 360/720 px queues: no clipped chip or shadow, and matching button right edges.

Independent read-only review covered base `d93037008bfcdc225cfc206b42002ed041ccdb38`, committed head `93b53acb3ad43061987d3d70a2acc03c563e3cb2` and the status/history working delta, with no remaining actionable findings. Full provider, reload/reconnect end-to-end and load campaigns were excluded; hook tests cover history reconstruction and stream outcomes. The existing queue review and its fixed race findings remain recorded in the PR.

## 3. Approved refresh persistence extension

- [x] 3.1 Mirror known waiting/unread indicators in bounded best-effort sessionStorage and restore them without restoring queues or live turns.
- [ ] 3.2 Test reload, reconciliation/read/deletion, malformed or unavailable storage and bounded retention; review, run root quality, sync docs/spec and update the existing PR.
