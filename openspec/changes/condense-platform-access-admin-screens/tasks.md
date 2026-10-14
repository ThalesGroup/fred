Written after the implementation (see proposal.md, Process note). Ticked items are on the branch `feat/platform-access-ui-condense`; their verification is the evidence block at the end unless a task names its own test.

## 1. Density and grouping

- [x] 1.1 Page, dialogs and tables on the sibling admin pages' scale (body-medium text, small tables and controls, 1080px cap, page-scoped font-token override removed); verified on screen by the product owner.
- [x] 1.2 Remove the duplicate Whitelist and Teams headings and the nested cards; move the whitelist reminder above the sub-tabs; verified by the page test "names each whitelist panel through its tab only".
- [x] 1.3 Filtering status badge beside the page title; verified by the page test "states next to the title whether filtering is on".

## 2. Rule editor and test result

- [x] 2.1 Conditions section: AND/OR radio group shown with two or more conditions, add button in the header, new condition scrolled into view; verified by the editor tests "offers the combination choice only when several conditions exist" and "keeps the add button in the conditions header, before the list".
- [x] 2.2 Each condition as one aligned row under a single heading line, every control named; verified by "lays each condition out as one row under a single heading line and names every control" and "labels the case switch with its visible text".
- [x] 2.3 Test, discard and save on one action row with the save state beside the button; verified by "groups test, discard and save in one row with the save state beside the button".
- [x] 2.4 Two result banners, the rule banner judged for the selected mode, an unchecked rule never accepting; verified by "judges the rule banner from the selected filtering mode", "never counts a rule that could not be checked as accepting, in either mode" and "colours the access banner by its own outcome, whatever the rule banner says".
- [x] 2.5 Name what keeps access from the administrator's own row of the existing users query; verified by "names what keeps the access: none known, one source, several sources" and "does not name the saved rule as a source when the tested rule refuses the account".
- [x] 2.6 Condensed field picker and value prompt, selected field in the action bar; verified by "shows the picked field in the picker's action bar, beside its buttons".

## 3. Whitelist tab and dialogs

- [x] 3.1 Shared search input, table selection with page-level select-all, contextual bulk bar, no-match line and spinner; verified by the page tests "shows the selection bar only while users are selected and clears it on request", "selects every user of the page from the table header", "keeps the selection unchanged while a grant is being saved" and "says so when a search matches no user and shows progress while searching".
- [x] 3.2 Activation dialog: warning-coloured missing-import notice, one spinner, shared disclosure for unchecked accounts; covered by the existing activation tests of the page.
- [x] 3.3 Invitation-links dialog: cleanup in the footer, Create link beside the filter, shared bounded-height rule, error-coloured revoke confirmation; verified by "keeps cleanup in the dialog footer, away from the status filter".

## 4. Copy and documentation

- [x] 4.1 Rewrite the French and English strings in plain terms and delete unused keys; verified by `npx prettier --check` on both locale files and the passing tests that read them.
- [x] 4.2 Replace the invented custom property, hand-mixed tints and hard-coded accent borders with existing tokens; verified by reading the stylesheet diff.
- [x] 4.3 Update `docs/swift/ux/COMPONENT-UX.md`, "Platform access screens".
- [x] 4.4 Write this OpenSpec change after the fact; `openspec validate condense-platform-access-admin-screens --strict` reports it valid (2026-10-14).
- [x] 4.5 Add the English migration note `docs/swift/ops/migrations/3087-condense-platform-access-admin.md` (impact none); `make migration-check` reports "Migration notes valid: 1 new declaration(s)" (2026-10-14).

## 5. Still to do

- [x] 5.1 Run `make code-quality` and record the result here. Run from `apps/frontend`, the only project this branch touches (tsc, prettier, eslint: clean, 2026-10-14); the root target was not run.
- [x] 5.2 Run the frontend `make test` (full suite) and record the result here: 330 files passed, 1 skipped; 4121 tests passed, 7 skipped (2026-10-14).
- [ ] 5.3 Check in a browser where focus lands when the invitation-links dialog opens (design.md, Open Questions b) and that keyboard order through the filter, Create link and the footer is usable.
- [ ] 5.4 Check on screen: the conditions row wrapping below 700px, the page in the dark theme, and the two banners with a screen reader (one status region).
- [ ] 5.5 Get the reviewer's answers to design.md Open Questions (a), (a2) and (b) to (e) and open follow-up issues where one is wanted.
- [ ] 5.6 Align the #3086 change `whitelist-lists-individual-exceptions` with this delta as listed in design.md, "Coordination with #3086", on its own branch.
- [ ] 5.7 Archive this change after merge and before #3086's.

## 6. Pre-PR review fixes

- [x] 6.1 A failed test or save is always shown and never beside "Rule saved": the error clears the saved state, and the saved confirmation lives only beside the Save button; verified by "shows a failed test after a save instead of the saved state" and "keeps the saved state after a successful test".
- [x] 6.2 The access banner never shows a team identifier: a team without a name is counted in a neutral localized wording (fr, en, singular and plural); verified by "never shows a team identifier when a team has no name".
- [x] 6.3 The Conditions title is an `h2`, directly under the page `h1`; verified by "keeps the add button in the conditions header, before the list" (level) and the page test "names each whitelist panel through its tab only" (no heading in the whitelist panel).
- [x] 6.4 `COMPONENT-UX.md` uses the shipped labels "Opens (Ouvertures)" and "Copy link".
- [x] 6.5 design.md records the cost of the source lookup as a reviewer question (Open Questions c) and the two reviewer notes on row selection and lost focus (a, a2).

## Verification evidence

Reported by the implementation sessions, from `apps/frontend`, at the last admin-only commit of the branch:

- `npx tsc --noEmit`: clean.
- `npx prettier --config .prettierrc --check` on the admin `PlatformAccessPage` folder and both locale files: clean.
- `npx eslint src/rework/components/pages/admin/PlatformAccessPage`: clean.
- `npx vitest run src/rework/components/pages/admin/PlatformAccessPage src/rework/components/pages/admin/AdminTeamsPage`: 4 files, 103 tests passed.

Re-run on 2026-10-14 at `e4dfeb459` while writing these artifacts: `npx tsc --noEmit` exit 0; the same vitest command, 4 files, 103 tests passed. Prettier and eslint were not re-run.

Not run: `make code-quality`, `make test`, the full frontend suite, any browser automation. The product owner checked the screens by hand during the sessions; no screenshot evidence is recorded.

Re-run on 2026-10-14 after the pre-PR review fixes (section 6), on the branch tip:

- `make code-quality` from `apps/frontend` (`npx tsc --noEmit`, prettier check, eslint): exit 0, all clean.
- `make test` from `apps/frontend` (full vitest suite with coverage): 330 files passed, 1 skipped; 4121 tests passed, 7 skipped.
- `npx vitest run src/rework/components/pages/admin/PlatformAccessPage`: 3 files, 94 tests passed.
- `make migration-check` from the repository root: "Migration notes valid: 1 new declaration(s)".
- `openspec validate condense-platform-access-admin-screens --strict`: valid.

Still not run: the root `make code-quality`, any browser automation.
