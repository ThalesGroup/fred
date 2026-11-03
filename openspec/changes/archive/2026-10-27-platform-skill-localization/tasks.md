## 1. Localized presentation

- [x] 1.1 Add a shared builtin-aware frontend title/description helper and en/fr dictionaries; verify fallback/custom collisions (#3077).
- [x] 1.2 Integrate menus, composer/history badges, previews and actual load activity; verify canonical selection/copy/recall and language switching.
- [x] 1.3 Regenerate provenance consumers and verify compatible old history/catalog behavior.

## 2. Integration

- [x] 2.1 Run focused frontend checks, root quality/offline checks and independent review; reconcile and archive.

Evidence: regenerated both clients; frontend full coverage suite passes 4813
tests (8 skipped), themes 14 tests, proxy checks, TypeScript, ESLint and Prettier.
After independent review, cross-turn canonical copy and focused-toggle fixes
pass 132 affected tests; reviewer independently reran 32 relevant tests. Native
separator fixtures preserve forward/backward selection and repeated identical
localized prose. Browser rendering status remains recorded in COMPONENT-UX.md.
Native Chromium subsequently passes six cross-message copy cases with real
separators and restored selection direction. A smoke check of the actual panel,
React, Switch, DataTable and CSS (only API hooks simulated) confirms stable
focus/scroll during save/refetch, one request under repeated activation, and
correct state after authoritative refresh. Product/design visual sign-off is
outside this implementation's functional verification.
