## 1. Prerequisites

- [x] 1.1 Archive `add-patch-note-announcements` (merged in PR #3022) in its own commit, and verify `openspec/specs/platform-announcements/spec.md` lists the patch-note requirements this delta modifies and removes
- [ ] 1.2 Get owner or reviewer confirmation of native drag and drop versus a library (design.md "Open Questions") and update task 6.3 if a library is chosen; verify with `openspec validate browse-patch-note-history`

## 2. Backend: data model

- [x] 2.1 In `models/announcement_models.py`, remove the partial unique index, add the nullable `position` column, replace `AnnouncementDismissalRow` by the per-user "last seen announcement" row, and update `table_ownership.py` and the docstrings; verify the model and ownership tests pass
- [ ] 2.2 Add one Alembic migration (drop the index, add and backfill `position` by creation date descending, drop `platform_announcement_dismissal`, create the per-user table) parented on the current `swift` head, re-parented before the PR with no merge revision, with the downgrade described in design.md; verify `alembic heads` shows one head, `alembic upgrade head` and a downgrade/upgrade round trip pass, and add a migration test covering the backfill. Done so far: revision `e5ff6d80cc9f` on `93427a5fe874`, one head, upgrade/downgrade/upgrade round trip and backfill covered on SQLite by `test_patch_note_announcement_migration.py`. Left: a real `alembic upgrade head` on PostgreSQL, and the re-parenting check before the PR

## 3. Backend: visibility and order

- [x] 3.1 Delete `disable_other_patch_notes`, the `409` branch, `delete_dismissals` on enable, `auto_disabled_ids`, `dismissal_count`, `AdminAnnouncement` and `count_dismissals`; verify with tests that two patch notes can be enabled and that enabling one records a single `activated` event
- [x] 3.2 Place a new patch note at the top on create and expose `position` on `Announcement`; the admin list returns patch notes by position; verify with tests, including that a patch note is created disabled by default
- [x] 3.3 Add `PUT /admin/platform/announcements/patch-notes/order` (full ordered id list, one transaction, `409` on a list that is not the current set, audit record, no activation event); verify with tests for a valid reorder, a stale list, a list naming a banner, and `403` for a non-administrator

## 4. Backend: announcing and seen

- [x] 4.1 Add `POST` and `GET /admin/platform/announcements/patch-notes/announcement`: the POST appends an `announced` activation event snapshotting the visible patch note at position 1 and emits an audit record, and answers `409` when no patch note is visible; the GET returns the newest one or null; verify with tests for both, and `403` for a non-administrator
- [x] 4.2 Replace `GET /announcements/patch-note` and `ActivePatchNote` with `GET /announcements/patch-notes` returning `PatchNoteHistory { patch_notes, pending_announcement_id }`; verify with tests for order, hidden notes left out, no announcement, pending per caller, null when nothing is visible, and `401` when unauthenticated
- [x] 4.3 Replace `PUT /announcements/{id}/dismissal` with `PUT /announcements/patch-note-announcements/{id}/seen` (idempotent, `404` on an id that is not an `announced` event, never moves a user back to an older announcement); verify with tests, including "a newer announcement made meanwhile stays pending" and "a record applies to the caller only"
- [x] 4.4 Verify with tests that creating, editing, deleting, reordering and toggling patch notes leave every caller's `pending_announcement_id` unchanged, as long as one patch note stays visible
- [x] 4.7 When a toggle-off or a delete leaves no visible patch note and an announcement is current, append an `unannounced` event in the same transaction (design.md decision 4b); verify with tests that nothing is pending afterwards for any user, including once a patch note is visible again, that the admin read returns null, that a new announcement is pending for everyone, that hiding one of several visible notes cancels nothing, and that nothing is appended when there is nothing to cancel
- [x] 4.5 Swap the user-deletion cleanup in `users/api.py` to the per-user row; verify `test_user_delete_route.py` passes
- [x] 4.6 Run `make code-quality` and `make test` in `apps/control-plane-backend`, plus `ruff --select I` and basedpyright as CI does; verify all are green

## 5. Contract

- [x] 5.1 Regenerate the client with `cd apps/frontend && make update-control-plane-api` (never hand-edit `openapi.json` or `controlPlaneOpenApi.ts`); verify the diff shows only the announcement routes and models
- [ ] 5.2 Update the tags and friendly aliases in `controlPlaneApiEnhancements.ts` for the new routes; verify `tsc` passes
- [x] 5.3 Add a dated entry to `CONTROL-PLANE-PRODUCT-CONTRACT.md` extending section 61 (visibility, position, announcement event, per-user seen, route table, removed routes, `409` and `dismissal_count`); verify section 61's superseded statements point to it

## 6. Frontend: admin page

- [ ] 6.1 Turn the page views into `banners | patchNotes | history`, each list split by kind with its own empty state and its own create button; delete `AnnouncementKindChooser`; verify with `AnnouncementsPage.test.tsx`
- [ ] 6.2 Patch-note rows: drag handle at the left, title, visibility `Switch` with hints, Preview, Edit, Delete; no confirmation on toggle, no user count; existing tokens only, neutral borders on `outline-*`; verify with tests that turning on B leaves A on
- [ ] 6.3 Reordering as decided in task 1.2 (default: native drag and drop on the handle, Arrow Up and Arrow Down on the focused handle, live-region announcement, optimistic update with rollback); verify with tests for a drop, a keyboard move, the announced text, and rollback on a `409`
- [ ] 6.4 "Announce the update" / "Annoncer la mise à jour" button on the Patch notes tab with its confirmation (number of visible patch notes and the one that opens first), disabled when none is visible, and the last-use text with the administrator's display name through `useUsersByIdsQuery`; verify with tests for confirm, cancel, disabled state and the last-use text
- [ ] 6.5 `PatchNoteEditorDialog`: keep plain save and "save and make visible", remove `replacesTitle` and its confirmation, keep the unsaved-changes confirmation; verify with `PatchNoteEditorDialog.test.tsx`
- [ ] 6.6 `ActivationHistory`: show and filter the `announced` and `unannounced` actions; verify with `ActivationHistory.test.tsx`

## 7. Frontend: user dialog

- [ ] 7.1 Give `PatchNoteDialog` an ordered list of notes, a position state reset on open, and the navigation (two `IconButton`s, medium, `on-surface-retreat`, around the `1 / 4` text, left towards position 1, right towards older) in `Dialog`'s `footerStart`; remove the checkbox, `showDontShowAgain` and their styles; verify with component tests for positions, disabled ends, no navigation with one note, and body shown from its top after moving
- [ ] 7.2 Replace `useActivePatchNote` with a hook returning the resolved history (notes without text in the viewer's or fallback locale left out) and the pending announcement id; verify with a unit test
- [ ] 7.3 Rewrite `PatchNoteGate`: open when an announcement is pending and the history is not empty, record that announcement as seen on close, stay closed for the page view if the write fails; delete `patchNoteSession.ts` and its test; verify with `PatchNoteGate.test.tsx`
- [ ] 7.4 Make the profile menu's "What's new" open the same dialog with the history, hidden when the history is empty; verify with `UserProfile.test.tsx`
- [ ] 7.5 Preview from the list and the editor uses the dialog with a single note; verify no seen record is sent
- [ ] 7.6 Update `fr` and `en` locales (tab labels "Bandeaux" / "Banners" and "Patch notes", navigation, reorder and announce labels, last-use text, `announced` action) and remove the unused keys (`dontShowAgain`, `dismissFailed`, `dismissalCount`, `activate.*`, kind chooser); verify no missing or orphan key with the locale checks in `make code-quality`

## 8. Documentation

- [ ] 8.1 Update the Help Center `features/administration.md` in `fr` and `en` (three tabs, toggle, ordering by drag and drop or keyboard, announcing, no "Don't show again", no "one active at a time") in a non-technical tone; verify both languages cover the same points
- [ ] 8.2 Update the Help Center `getting-started/first-steps.md` in `fr` and `en` ("What's new" opens the history and how to move through it); verify both languages match
- [ ] 8.3 Update `docs/swift/ux/COMPONENT-UX.md` (`PatchNoteDialog` / `PatchNoteGate`, patch-note row and reordering, announce button, tabs, editor); verify it names no removed component
- [x] 8.4 Add the English migration note under `docs/swift/ops/migrations/` from the template in `MIGRATION-GUIDES.md` (no operator action; earlier "Don't show again" choices are discarded; no dialog until an administrator announces; one visible patch note after upgrade); verify the release checks accept it
- [ ] 8.5 Check `.claude/skills/write-patch-note/SKILL.md` for wording that assumes a single active patch note shown on activation and update it if so; verify by reading it against the new behaviour

## 9. Verification and close-out

- [ ] 9.1 Warn the owner, then run the root `make code-quality` and the frontend `make test`; restart Vite afterwards; verify all are green
- [ ] 9.2 Manual check on a local stack: create three patch notes (off), turn two on, reorder by mouse and by keyboard, confirm no dialog at sign-in, announce, confirm the dialog opens once per user on position 1 with navigation, confirm editing and toggling do not reopen it, turn all off and confirm "What's new" disappears, the button is disabled and its last-use text is gone, then turn one on again and confirm no dialog opens for a user who had not seen the announcement
- [ ] 9.3 Run the author review from `AGENTS.md` and record exact test evidence in `verification.md`; verify every spec scenario maps to a test or a recorded manual check
