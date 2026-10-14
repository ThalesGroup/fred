## Why

The Platform access administration screens are harder to read than their sibling admin pages (GitHub issue #3087): headings repeat the tab they sit under, cards are nested, body text and controls are one size larger than elsewhere, and the rule test shows one green panel saying both that access is kept and that the account does not match the rule, without saying what keeps the access.

## Process note

This change was implemented before this OpenSpec change existed. The product owner asked for a visual trial first ("try it and we'll see") and then kept iterating on it on screen, commit after commit. These artifacts were written afterwards, from the diff of `feat/platform-access-ui-condense` against `swift` and its commit messages; they record what was built and what is still unverified. They did not precede the code, and Step 1 of the task lifecycle was not followed. `tasks.md` ticks what is done and leaves open what is not.

## What Changes

Frontend only. No endpoint, payload, permission or admission rule changes.

- **Density.** Body text follows the sibling admin pages, section titles no longer reuse the page-title size, tables use the small row height, secondary controls use the small tier, and the page is capped at the capabilities page width. **This reverses the typography decision recorded on 2026-10-05** (larger body text and section headings on this page).
- **Grouping.** The Whitelist panel and its Users/Teams sub-panels are named by their tabs only: the duplicate "Whitelist" and "Teams" headings and the nested cards are gone. The reminder that whitelist entries always grant access moves from the rule editor to the top of the Whitelist tab. A status badge beside the page title says whether filtering is on.
- **Rule editor.** Conditions get their own section: the AND/OR choice (shown only with two or more conditions) and the add button sit in its header, each condition is one aligned row under column labels shown once, and test, discard and save share one action row with the unsaved/saved state beside save. The card title repeating the tab name is removed.
- **Rule test result.** Two banners replace the single panel: whether the tested rule accepts the account (judged for the selected allow/block mode), and whether the account keeps access once filtering is on. Each is coloured by its own outcome. When access is kept, the second banner names what keeps it.
- **Whitelist users.** Shared search input on one row with the one-time import, row selection through the table's own selection (with a page-level select-all), a bulk bar shown only while users are selected, a "no match" line and a spinner while searching.
- **Field picker and value prompt.** Narrower dialogs; search and the advanced/simple switch share one row; the selected field moves into the action bar.
- **Activation and invitation-link dialogs.** Warning-coloured notice for the missing import, one spinner for the review refresh, the shared disclosure for accounts that could not be checked; the cleanup action moves to the dialog footer, away from the status filter; revoking confirms in the error colour.
- **Copy (fr, en).** No more "token", "claim", "dry run" or "delegated requests"; one term per concept. Three visible labels the spec names change: "Verification unavailable" becomes "Not checked", "Copy URL" becomes "Copy link", and the opening-count column "Accesses (Accès)" becomes "Opens (Ouvertures)".
- **Removed explanations.** Two sentences the current spec requires are no longer displayed: the hint that rule edits apply only after an explicit save when filtering is active, and the definition of what the opening count measures. See design.md, Open Questions.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `platform-access-control`:
  - "Access administration has readable section navigation": no heading repeating a tab, one whitelist reminder above the sub-tabs, a filtering status indicator beside the title, the sibling pages' body size instead of the page's own larger scale.
  - "Administrators compose understandable bounded predicates": conditions section and aligned rows, one action row replacing the save action near a title, two-statement test result naming the sources of kept access.
  - "Activation and migration are explicit": the section for accounts that cannot be evaluated is named "Not checked".
  - "Administrators manage independent Free-link history": "Copy link" and "Opens (Ouvertures)" labels; the counting definition is no longer required on screen.

## Impact

- `apps/frontend/src/rework/components/pages/admin/PlatformAccessPage/`: page, rule editor, field picker, value prompt, activation dialog, invitation-links dialog, both stylesheets, three test files.
- `apps/frontend/src/locales/{fr,en}/translation.json`.
- `docs/swift/ux/COMPONENT-UX.md`, "Platform access screens".
- One migration note, impact none.
- No backend, OpenAPI, generated client, shared component, configuration or data change. The rule tester issues one additional read on the existing admin users endpoint (see design.md).
- Coordination: the stacked change `whitelist-lists-individual-exceptions` (#3086) modifies "Access administration has readable section navigation" again and must be archived after this one (see design.md).
