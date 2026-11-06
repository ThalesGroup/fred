## 1. Tree state

- [x] 1.1 Lift tree state into `TeamWikiPage`: per-user localStorage entry with per-team `expanded` + `lastSlug`; `WikiTree` receives `expanded` and `onToggle`. Verify with a test: first render is fully collapsed, toggles survive a remount.
- [x] 1.2 No slug in URL → open stored `lastSlug` if it still exists, else first page; record the opened slug. Verify with tests for both cases.
- [x] 1.3 Expand the ancestors of the active page and persist them. Verify with a test on a nested direct link.

## 2. Edit mode

- [x] 2.1 Remove rename and delete icons from `WikiArticle`, and delete the rename `Dialog`, its state and `renameDialog` i18n keys (fr/en). Verify the reading view shows only History + Edit.
- [x] 2.2 `WikiEditor`: editable title field and parent select (root + `moveTargets`) for ordinary pages; fixed title for rules. Verify with a test for both page kinds.
- [x] 2.3 Delete `IconButton` (`color="error"`, tooltip "Supprimer la page" / "Delete page") on the left of the editor actions, opening the existing confirmation. Verify with an interaction test.
- [x] 2.4 Save: metadata PATCH when title/parent changed, then content PUT; duplicate title keeps the editor open. Verify with interaction tests.

## 3. Close-out

- [ ] 3.1 `make code-quality` and frontend `make test` green; migration note added; manual check in the UI.
