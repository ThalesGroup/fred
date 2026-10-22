## 1. Discovery and persistence

- [x] 1.1 Keep OpenAI-compatible discovery and mixed static/discovered catalogs; add safe live refresh and focused pod tests.
- [x] 1.2 Extend this PR's one Alembic revision with source inventory and fallback storage; add store tests.

## 2. Control-plane contract

- [x] 2.1 Add authorized URL read/write/reset and refresh APIs; persist successful inventory diffs and report failures without removals.
- [x] 2.2 Deliver effective URL and confirmed removals to pods, plus the distinct fallback in trusted managed runtime bindings; test turn behavior.
- [x] 2.3 Retain removed rows for admin inspection while excluding them from new grants and choices; test static and mixed catalogs.

## 3. Admin UI and documentation

- [x] 3.1 Regenerate API clients and show URL editor, refresh result, new/removed summary, and unavailable rows in Features > Models; add focused UI tests.
- [x] 3.2 Add a fallback model control alongside the forced binding; update EN/FR strings, catalog YAML comments, and operator guide with the OpenAI response limitation.

## 4. Close-out

- [x] 4.1 Run root code-quality once, review the full PR against `swift` with independent read-only review, reconcile and archive the spec, push the draft PR, and confirm green CI.
