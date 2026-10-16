## Context

See proposal.md for motivation and for the process note: this document describes decisions already taken in code, in the order the product owner settled them on screen.

The page had its own type scale since 2026-10-05 (`docs/swift/ux/COMPONENT-UX.md`, "Platform access screens": 16px body, 14px guidance, 22px section headings, obtained partly by overriding the body-small font token inside the page). The sibling admin pages use 14px body text, small tables and small controls.

The rule preview endpoint answers three things for the connected administrator: whether the draft matches, the per-condition reasons, and whether they would be admitted with filtering on. It does not say which sources admit them. The admin users endpoint does, per user.

## Goals / Non-Goals

**Goals:**

- Reach the density and grouping of the sibling admin pages using existing component props and tokens only.
- Make the rule test result state each fact once, with its own outcome.

**Non-Goals:**

- No new prop on a shared component, no new design token.
- No backend, contract or admission-logic change.
- The Whitelist tab's content and navigation depth: handled in #3086.

## Decisions

- **Sibling type scale instead of the page's own.** Page and dialog bodies use `--font-body-medium`; guidance keeps that size and takes `on-surface-retreat`; the only remaining section title (Conditions) is an `h2` in `--font-title-small`, so the heading levels do not skip one under the page `h1`. The page-scoped override of `--font-body-small` is deleted. Tables use `size="small"`, controls the small tier (32px tier inside a condition), and the page is capped at 1080px. Alternative: keep the 2026-10-05 scale and only regroup. Rejected by the owner on screen: the page stayed visibly larger than its neighbours.
- **Tabs name the panels.** The headings repeating "Whitelist" and "Teams" are removed, with the cards around them. One sentence above the sub-tabs carries the reminder that whitelist entries always grant access; it replaces the same reminder in the rule editor.
- **Filtering status as a `StatusBadge` in the header's `titleAction`,** success tone when on, neutral when off, rendered once the state is loaded. The header action stays the only control.
- **Conditions as a grid, not a table.** Each condition stays a `fieldset` with a screen-reader legend. A heading line above the list is `aria-hidden`; every control carries its own accessible name, and per-condition labels come back when the row wraps (container narrower than 700px). Alternative: a real table. Rejected: the row must reflow on narrow screens and hosts a regex hint and a per-condition result under it.
- **Add button in the section header.** It no longer moves down as conditions are added; the new condition is scrolled into view instead.
- **AND/OR as a radio `ButtonGroup`, hidden with fewer than two conditions.** The stored combination is untouched while hidden.
- **One action row.** Test, Discard and Save at the bottom of the rule, the unsaved/saved state beside Save, the result directly under the row. The title "Admission rule" and the Save button beside it are removed.
- **Two banners for the test result.** Rule banner: accepted or not, judged for the selected mode; a condition that timed out or could not be inspected makes the banner an error in both modes. Access banner: kept or lost, from the preview's `admitted`. Each uses the success or error container colours of its own outcome, so a rejected rule beside kept access shows one red and one green banner instead of one green panel.
- **Naming the sources with the existing users query.** After a test that keeps access, the editor requests the admin users listing with the administrator's username as search text (`limit` 100) and reads their own row by user id. It names the platform administrator role, the individual access (manual or initial import, one wording) and each authorized or link-access team by name; a team whose name is missing is counted in a neutral wording ("an authorized team", "2 authorized teams") and its identifier is never shown; the row's rule source is ignored because it reflects the saved rule, and "the rule" is named only when the tested draft accepts the account. Without the row, the banner states the outcome alone. Alternative: extend the preview response with sources. Rejected for this change: it is a contract change, out of the issue's scope.
- **Table selection through `DataTable`'s `selectable`.** It replaces a hand-built checkbox column and brings a page-level select-all. The selection set is owned by the page, so it still survives searches and pages; changes are ignored while a save is in flight.
- **Cleanup in the dialog footer.** The destructive action leaves the row it shared with the status filter; Create link takes its place at the right of that row.
- **Stylesheet cleanup in the same branch.** An invented result-accent custom property, hand-mixed tints and hard-coded accent borders are replaced by existing container and state tokens.

## Coordination with #3086

The branch `feat/platform-access-whitelist` is stacked on this one. Its change `whitelist-lists-individual-exceptions` also modifies "Access administration has readable section navigation": one navigation level with three tabs (Rules, Users, Teams) replaces the Whitelist tab and its sub-tabs.

Order: archive this change first, then #3086's. A MODIFIED requirement replaces the whole block, so archiving them the other way round would bring the sub-tabs back.

This change's version of the requirement is the state after #3087 alone: two tabs, Users/Teams sub-tabs, no duplicate heading, the sibling type scale. #3086's delta was written against the pre-#3087 text. To stay consistent it must carry over, word for word, what this change adds:

- Replace "Ordinary content, secondary explanations and section headings SHALL use a consistent readable typography scale across the page and its dialogs." with "Ordinary content and secondary explanations SHALL use the body text size of the sibling administration pages across the page and its dialogs, secondary explanations being set apart by a subdued colour rather than a different size. No section heading SHALL reuse the page-title size."
- After the sentence about the top-right filtering action, add "Once the filtering state is known, a status indicator beside the page title SHALL state whether filtering is on or off, on every tab."
- In the scenario "Read page and modal content", use "ordinary text and secondary help SHALL use the body text size of the sibling administration pages, with errors and revocation guidance retained".
- Add the scenario "Filtering status beside the title" unchanged.

What #3086 legitimately replaces and need not keep: the two sentences saying the whitelist panels are named by their tabs only and state the reminder once above the sub-tabs. With three top-level tabs there is no Whitelist tab left to name them, and #3086 gives Users and Teams a heading and a description each. Its headings must respect "No section heading SHALL reuse the page-title size".

This change does not modify "Platform administrators manage live exceptions", so nothing there needs aligning. Nothing in #3085's requirement ("Admission feedback uses the shared Fred error presentation") is touched here.

## Risks / Trade-offs

- [The rule tester issues one more request] → only after a test that keeps access, on an existing paginated endpoint, and the result is cached by the query layer.
- [The source list can be incomplete] → the banner falls back to the outcome alone; see Open Questions (c).
- [Copy is shorter, so some precision is lost] → see Open Questions (e).
- ["Administrators filter invitation history by lifecycle status" asks for a "bounded fixed height"] → the history table was already sized from its row count up to a cap; it is now content-sized under the same cap as the activation review, with the header and pagination still outside the scrolling body. The requirement is left as is; say so if "fixed" was meant literally.
- [The cleanup action's new place and the whitelist table's selection bar are not specified] → presentation of unchanged behaviour, described in `COMPONENT-UX.md` only. #3086 removes row selection from this table.

## Open Questions

For the PR reviewer. None blocks the code as built; each may lead to a follow-up.

- **(a) Row selection through the shared table.** Reviewer note: on this branch alone, the row checkbox has the table's generic localized label ("select row") where the page used to name the user ("Select alice"), and it shows no disabled state: during a save the page ignores selection changes but the checkboxes still look active. Fixing either needs a new `DataTable` prop, which the issue excludes. Both disappear with #3086, which removes row selection from this table, so the two PRs should merge close together. Acceptable until then?
- **(a2) Focus after the selection bar goes away.** Reviewer note: the bar is unmounted when the selection becomes empty, so keyboard focus is lost (it falls back to the document) after "clear selection" and after a successful bulk grant, both of which are triggered from inside the bar. Not fixed here for the same reason as (a): #3086 removes row selection and the bar from this table. Is that acceptable for the time the two PRs are apart?
- **(b) Invitation-links dialog focus.** The shared dialog focuses its first control. That used to be Create link; with Create link moved to the right of the filter row, it is now the status filter. Established by reading the code, not checked in a browser. Is that the wanted landing point?
- **(c) Naming the access sources.** One extra request to the admin users endpoint, searching the administrator's own username and capped at 100 matches: if more than 100 accounts match that text, the administrator's row may be missing and the banner states the outcome without sources. The banner also names "the rule" whenever the tested draft accepts the account, but the backend ignores a rule match when the stored account data is flagged as conflicting for the same token; the page cannot detect that rare case and may then name the rule beside the real source, or show an accepting rule above a lost access. The lookup is also not cheap: it asks for up to 100 rows with a substring search, and the backend computes the admission sources row by row, so a single test can cost up to 100 per-row source computations to read one row. Reviewer question: should the preview response carry the tested administrator's own sources instead (a dedicated self-sources answer, one computation, no search and no 100-match limit)? That is a contract change, left out of this issue.
- **(d) Typography.** This reverses the 2026-10-05 decision (16px body, 22px section headings on this page) in favour of the sibling pages' scale. Decided by the owner on screen; please confirm.
- **(e) Explanations and labels the spec named.** Removed from the screen: the hint that rule edits apply only after an explicit save when filtering is active, and the sentence defining the opening count (page openings after sign-in, not people who joined). Renamed: "Verification unavailable" to "Not checked", "Copy URL" to "Copy link", "Accesses (Accès)" to "Opens (Ouvertures)". The delta spec follows the code on all five points. Should either explanation come back, for instance as a tooltip?
