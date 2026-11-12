## 1. Recorded usage propagation

- [x] 1.1 Add scoped optional provider counters to runtime events and history; verify provider aliases, missing/invalid/zero values, serialization and unchanged batch billing with focused tests.
- [x] 1.2 Regenerate the runtime client and connect live metadata to the drawer; verify live and reloaded values agree and unknown-tool redaction remains intact.

- [x] 1.3 Forward final per-model API usage and select the first response after the result by exchange/rank; verify exact 103991/2956 live/reload association and absence of requesting-call/other-turn fallback.

## 2. Presentation and local recovery

- [x] 2.1 Combine preview notes into one localized compact sentence; verify real rendered syntax colors, bounds and copy text in French and English.
- [x] 2.2 Recover the reported local session's counters by exact recorded tool-call identity with metadata backup; verify the reported new session shows input 103991 and output 2956 for the exchange after SQL without changing billing.
- [x] 2.3 Verify the real captured step in the browser at desktop and mobile widths and record screenshots and limitations.

## 3. Review and close-out

- [ ] 3.1 Update existing contracts, UX guidance and migration note; verify root quality, migration check and strict OpenSpec validation.
- [x] 3.2 Complete author branch audit and fresh independent runtime/performance review; resolve findings and record scope/evidence in the existing PR.
- [ ] 3.3 Reconcile tasks, sync/archive the change, commit and push reviewable blocks and update issue #3527 and draft PR #3528.

Verification in progress: provider/runtime tests 48 passed; focused history persistence tests 19 passed; frontend suites 370 passed. Existing history endpoint TestClient cases stalled in this sandbox and were interrupted; they are not claimed as covered. Browser replay uses the real drawer and new stored step 6: badges 103991/2956, visible API/full-context scope, original syntax colors and one compact French notice, verified at 1280px light and 375px dark. The authenticated full conversation could not be driven through Chrome; screenshots are an isolated replay. The developer clarified API metrics must describe the exchange following the result (new session 103991/2956), not the requesting call (20077/644), and chose API-only metrics without a tokenizer. Trace input matches the complete 189642-character result and its tool-call ID exactly. Private recovery backups are in /tmp and excluded from Git; all other fields, including billing, were verified unchanged. Independent review found missing-count provenance and inaccessible hover-only scope; fixes prioritize raw provider presence and show scope visibly. Fresh independent full-branch/runtime/performance review rechecked all four findings and found no remaining actionable defects; it independently reran the 48 + 19 backend tests. Full root quality evidence follows in the existing PR.
