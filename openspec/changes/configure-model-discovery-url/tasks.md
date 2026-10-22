## 1. Discovery and persistence

- [x] 1.1 Keep OpenAI-compatible discovery and mixed static/discovered catalogs; add safe live refresh and focused pod tests.
- [x] 1.2 Extend this PR's one Alembic revision with source inventory and fallback storage; add store tests.

## 2. Control-plane contract

- [x] 2.1 Add authorized URL read/write/reset and refresh APIs; persist successful inventory diffs and report failures without removals.
- [x] 2.2 Deliver effective URL and confirmed removals to pods, plus the distinct fallback in trusted managed runtime bindings; test turn behavior.
- [x] 2.3 Retain removed rows for admin inspection while excluding them from new grants and choices; test static and mixed catalogs.
- [x] 2.4 Project the pod-advertised discovery source onto admin model rows without guessing from names or IDs; cover static and discovered entries.

## 3. Admin UI and documentation

- [x] 3.1 Regenerate API clients and show URL editor, refresh result, new/removed summary, and unavailable rows in Features > Models; add focused UI tests.
- [x] 3.2 Add a fallback model control alongside the forced binding; update EN/FR strings, catalog YAML comments, and operator guide with the OpenAI response limitation.
- [x] 3.3 Separate manual and discovered model rows in Features > Models, clarify an unregistered source state, and loosen display-name form spacing; add focused UI coverage.

## 4. Close-out

- [x] 4.1 Run root code-quality once, review the full PR against `swift` with independent read-only review, reconcile and archive the spec, push the draft PR, and confirm green CI.
- [x] 4.2 Review and validate this follow-up, sync the spec, and rearchive the change.

## 5. Model administration follow-up

- [x] 5.1 Use pill tabs and a text filter for manual/discovered models, show every advertising pod, and replace the large discovery card with a compact refresh control.
- [x] 5.2 Replace free-form disappearance fallback with a manual chat-profile selector resolved at runtime; update this PR's single migration and focused tests.
- [x] 5.3 Exclude entries explicitly marked non-chat by `/models`, read Mistral's context field, and document the optional metadata and reasoning limitation.
- [ ] 5.4 Regenerate clients, run targeted and root checks, review the whole branch, sync and archive the spec, push the draft PR, and confirm green CI.

## 6. Multiple discovery URLs

- [x] 6.1 Support multiple named sources in one YAML catalog while preserving the single-source form, source ownership, unique IDs and one chat default.
- [x] 6.2 Refresh and advertise each source independently across runtime and control-plane, with retained inventories when another source fails.
- [ ] 6.3 Document the YAML form and add focused multi-source tests, then verify and update the draft PR with green CI.

## 7. Upstream model details

- [x] 7.1 Add an authorized, bounded on-demand `GET /models/{id}` proxy for a discovered model and cover its source routing.
- [x] 7.2 Show nested detail fields from a clickable information control, preserving context metadata already visible on the row.
- [ ] 7.3 Verify generated clients, documentation, branch review and green CI before updating the draft PR.
