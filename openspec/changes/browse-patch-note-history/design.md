## Context

See proposal.md for motivation; the owner decisions in issue #3080 are final
and are not reopened here. What the code does today (PR #3022):

- `platform_announcement.kind` is `banner | patch_note`; a patch note keeps its
  body in `description_long`. `enabled` is the only delivery state: there is no
  scheduling, no publication date and no position column.
- A partial unique index (`uq_platform_announcement_active_patch_note`,
  `enabled AND kind = 'patch_note'`) allows one enabled patch note. Enabling
  one disables the other in the same transaction, records a `deactivated`
  event for it, and can answer `409`.
- Enabling a patch note is what makes the dialog open at sign-in. "Don't show
  again" is one row per user and note in `platform_announcement_dismissal`,
  deleted when the note is re-enabled. Closing without the checkbox is
  remembered in the browser only (`patchNoteSession.ts`).
- `GET /announcements/patch-note` returns `ActivePatchNote { patch_note,
  dismissed }`; `PUT /announcements/{id}/dismissal` records a dismissal.
- `platform_announcement_activation_event` is append-only, has no foreign key,
  and carries `announcement_id`, `kind`, `label`, `action` (a 16-character
  string, `activated | deactivated`), `actor_uid`, `occurred_at` (indexed).
  The history view resolves `actor_uid` to a display name with
  `useUsersByIdsQuery`.
- The admin page has two views in a `ButtonGroup` `variant="tabs"`, one mixed
  list, and a kind chooser dialog on create.
- `PatchNoteDialog` puts the checkbox in `Dialog`'s `actionsAddon`, which sits
  beside the buttons on the right. `Dialog` also has `footerStart`, which is
  left-aligned in the action bar.
- **Drag and drop: nothing to reuse.** `apps/frontend/package.json` has no
  drag-and-drop or sortable library, and no component under `src/rework`
  implements a reorderable list.

Constraints: consolidation phase (prefer deletion), linear Alembic history,
generated API client, existing design tokens and components only.

## Goals / Non-Goals

**Goals:**

- Three independent controls: visibility (`enabled`), order (a position),
  announcement (an explicit event).
- No new table beyond the one that replaces the dismissal table; no new
  frontend dependency.
- Remove more than is added: the one-active rule, the per-note dismissals, the
  browser memory, the kind chooser, the checkbox, the user count.

**Non-Goals:**

- Scheduling an announcement, or announcing to a subset of users.
- A reusable drag-and-drop component for other pages.
- Any change to banners, their delivery, their dismissal or their editor.
- Writing helpers for the patch-note editor (#3017).

## Decisions

**1. Visibility is `enabled`.** A patch note's `enabled` column keeps its
route, its switch, its activation events and its audit records; it just stops
meaning "shown at sign-in". The partial unique index goes, and with it
`disable_other_patch_notes`, the `409` branch, `auto_disabled_ids` and the
frontend confirmation naming the replaced note. A patch note's
`content_version` no longer keys anything; the shared toggle code that bumps
it is left alone. Alternative: a separate `visible` column. Rejected: two
flags for one decision.

**2. Order is a nullable integer `position` on `platform_announcement`.**
Set for patch notes, null for banners. A new patch note takes the top place
and the others shift, in the create transaction. Reordering is one request,
`PUT /admin/platform/announcements/patch-notes/order`, carrying the full
ordered list of patch-note ids; the server rewrites positions in one
transaction and refuses (`409`) a list that is not exactly the current set, so
a stale page cannot silently drop or misplace a note. Alternative: a
"move by one" route. Rejected: a drag across several rows becomes several
requests. Alternative: fractional positions. Rejected: the list is small.
The admin list returns banners as today and patch notes by position.

**3. The announcement is an event in the existing activation history.**
Announcing appends one `platform_announcement_activation_event` row with
`action = "announced"`, `kind = "patch_note"`, the acting administrator and
the time; `announcement_id` and `label` snapshot the visible patch note at
position 1, which is what users will open on. "Last use and who" is the
newest `announced` row (one query on the indexed `occurred_at`). This needs
no schema change to that table and no new store, and the announcement shows
up in the history tab for free. Alternative: a dedicated one-row
"last announcement" table. Rejected: a second place recording who did what
and when. Trade-off: the event's `announcement_id` describes the note at
position 1 rather than "the" subject of the event; the history view shows it
as "Announced to users" with that title.

**4. "Seen" is one row per user, replacing the dismissal table.**
`platform_announcement_dismissal` (per user and note) is dropped and replaced
by a table keyed by `user_id` holding the id of the last announcement event
that user has seen and when. An announcement is pending for a user when a
newest `announced` event exists and the user's row does not name it. Rows are
removed with the user, where `delete_dismissals_for_user` is called today.
The client records the id it was shown, not "the latest", so an announcement
made between the read and the close stays pending; the server ignores a record
that would move a user back to an older announcement. Alternative: keep the
per-note table and write a row for position 1. Rejected: it breaks when that
note is deleted (cascade) or reordered. Alternative: a column on a user table.
Rejected: control-plane has no user table of its own to extend.

**4b. Hiding the last visible patch note cancels the announcement (owner
decision).** When a toggle-off or a delete leaves no visible patch note and
the newest announcement event is `announced`, the same transaction appends one
`action = "unannounced"` event (the hidden note's id and title, the acting
administrator). The *current announcement* is the newest event among
`announced` and `unannounced` when that event is `announced`, else none. That
one computation feeds `pending_announcement_id`, the admin "last use" read and
the cancel check, so they cannot disagree. Nothing stays pending: after a
cancellation only a new click on "Announce the update" opens the dialog, and
the last-use text is empty until then. Per-user rows are not touched; a row
naming a cancelled announcement is simply never current again. Alternative:
delete the `announced` row. Rejected: the history is append-only.
Alternative: keep it pending until a note is visible again (the first draft).
Rejected by the owner: a dialog would open long after the click, on content
the administrator never announced. `unannounced` fits the 16-character
`action` column, so the events table still needs no schema change.

**5. Routes.** Replacing, not adding beside:

| Method | Path | Permission | Purpose |
| --- | --- | --- | --- |
| GET | `/announcements/patch-notes` | authenticated | `PatchNoteHistory { patch_notes: Announcement[], pending_announcement_id: str \| null }`, visible notes in order |
| PUT | `/announcements/patch-note-announcements/{id}/seen` | authenticated | `204`, idempotent; `404` when the id is not an `announced` event |
| PUT | `/admin/platform/announcements/patch-notes/order` | `can_manage_platform` | full ordered id list; `409` when stale |
| GET | `/admin/platform/announcements/patch-notes/announcement` | `can_manage_platform` | the current announcement (`id`, `announced_at`, `announced_by`) or null when none was made or the last one was cancelled |
| POST | `/admin/platform/announcements/patch-notes/announcement` | `can_manage_platform` | announce; `409` when no patch note is visible |

Deleted: `GET /announcements/patch-note`, `ActivePatchNote`,
`PUT /announcements/{id}/dismissal`, `AdminAnnouncement.dismissal_count`
(the admin list returns `Announcement[]`, which gains `position`).
`AnnouncementActivationAction` gains `announced` and `unannounced`. The
history read stays once per application load, so "next sign-in" is in practice
"next load". `pending_announcement_id` is null when no patch note is visible.

**6. Dialog navigation in `footerStart`.** `PatchNoteDialog` takes the ordered
list of notes instead of one title and body, keeps the current position in
state, and resets to position 1 each time it opens. The navigation is two
`IconButton`s (default `size="medium"`, `color="on-surface-retreat"`) around
the position text, placed with `Dialog`'s existing `footerStart`, so `Dialog`
is not changed. Hidden with one entry, which is how the admin preview uses
it. The gate keeps a component state so a failed write cannot reopen the
dialog during the page view; `patchNoteSession.ts` and its test are deleted.

**7. Reordering without a new dependency (default).** Since nothing exists to
reuse, the default is native HTML drag and drop on the row's drag handle, plus
keyboard on that same handle: it is a focusable button, Arrow Up and Arrow
Down move the row one place, and the new place is announced through a live
region. Each drop or key press sends the full order and updates the list
optimistically, rolling back on error. This stays local to the Patch notes
list. Alternative: add a library such as `@dnd-kit` (touch support, smoother
feedback, built-in keyboard handling). Not chosen here because adding a
dependency is an owner and reviewer decision; if it is preferred, only task
6.3 changes.

**8. Admin tabs and editor.** `VIEWS` becomes `banners | patchNotes |
history`; the one admin list query is split by kind. Each tab's header button
creates its own kind, so `AnnouncementKindChooser` is deleted. The announce
button sits in the Patch notes tab with its last-use text beside it, uses the
existing `ConfirmationDialog`, and is disabled when no patch note is visible.
The editor keeps its two saves, plain (toggle untouched; off on create) and
"save and make visible"; only `replacesTitle` and its confirmation go. The
history view's action filter gains the `announced` action.

## Risks / Trade-offs

- [The predecessor change was merged but not archived, so the main spec lacked
  the requirements this delta modifies] → `add-patch-note-announcements` is
  archived first, in its own commit (task 1.1).
- [Other open PRs add migrations on the same parent, `93427a5fe874`] → this
  migration will need re-parenting onto the `swift` head before the PR, never
  a merge revision (task 2.2).
- [Native drag and drop is weak on touch screens and gives plain visual
  feedback] → the admin page is a desktop surface and the keyboard path covers
  the rest; the library alternative is listed for the owner.
- [An administrator announces before ordering or toggling as intended] → the
  confirmation says how many patch notes users will see and which one opens
  first.
- [An administrator hides the last visible patch note by mistake and loses
  the announcement for users who had not seen it] → intended (decision 4b);
  the cancellation is in the history and one click announces again.
- [The history view receives a fourth action, `unannounced`] → it needs a
  label and a filter entry beside `announced` (task 6.6).
- [A user created after the last announcement gets the dialog at first
  sign-in] → intended: it is new to them.
- [The history is loaded whole at every application load] → bounded by what
  the administrator keeps visible.

## Migration Plan

One linear Alembic migration:

1. Drop `uq_platform_announcement_active_patch_note`.
2. Add `platform_announcement.position` and backfill patch notes, most
   recently created first.
3. Drop `platform_announcement_dismissal`; create the per-user table.

No `announced` event is created, so nothing is pending and no user gets a
dialog after the upgrade. The patch note enabled before the upgrade stays the
only visible one. No operator action, configuration or chart value; the
migration note still declares `impact: minor`, which the migration-note check
requires of any new Alembic revision. Downgrade recreates the dismissal table
empty, keeps the top enabled patch note and disables the others before
recreating the index, drops the position column and the per-user table, and
deletes the `announced` and `unannounced` events the older code cannot read.

## Owner Decisions

Closed by the owner; written into the specs and tasks.

- Button label: "Annoncer la mise à jour" / "Announce the update", with the
  date of its last use and the administrator's name beside it.
- Arrows: left towards newer (position 1), right towards older.
- After upgrade: only the currently enabled patch note has its toggle on, the
  others are off, and no announcement is pending.
- Per-note user counter: removed.
- One create button per tab; the kind chooser is removed.
- Drag handle at the left of each card; the order is also changeable by
  keyboard.
- Turning off (or deleting) the last visible patch note cancels the pending
  announcement: users who had not seen it get nothing, and a new click on
  "Announce the update" is needed. Announcing is refused while no patch note
  is visible.

## Divergences From The First Draft

- Once the predecessor was archived, `openspec validate` refused every
  MODIFIED block that drops a scenario of the current spec. Four requirements
  are therefore replaced (REMOVED plus ADDED under a new name) instead of
  modified: the dialog at load, the admin list, the activation history and
  the authorization. In the editor safeguards the scenario keeps its former
  name, "Save and activate". No behaviour changed.
- Migration note impact is `minor`, not the "patch increment" first planned:
  `make migration-check` refuses `none` for a new Alembic revision.
- The contract entry is subsection 61.1, not a new numbered section, to stay
  out of the section-number collisions between open pull requests.
- The seen route is declared as `{announcement_event_id}` and the reorder
  route answers `204`; the per-user table is `platform_announcement_seen`.
- `GET /announcements/patch-notes` also checks that a patch note is visible
  before reporting a pending announcement: two administrators hiding the last
  two notes at the same moment can each miss the cancellation of decision 4b.
- The migration also updates the comment of the events table's `action`
  column, so that table is touched after all (comment only).
- New routes are listed in `docs/swift/platform/authz-endpoint-matrix.yaml`,
  which a backend test requires; the plan did not name that file.

## Frontend Divergences

- **Decision 7 is superseded and the "no new frontend dependency" goal is
  dropped**: the owner chose `@dnd-kit/core`, `@dnd-kit/sortable` and
  `@dnd-kit/utilities` for a smoother, animated reorder. The keyboard path is
  the library's (Space or Enter on the handle, arrows, Space or Enter again),
  not one Arrow press per move. The vertical-only constraint is a three-line
  modifier, so `@dnd-kit/modifiers` is not added.
- **Announce confirmation** carries both texts: the owner's sentence (every
  user gets the dialog at their next sign-in) and the plan's count and first
  note. The last-use slot shows nothing when no announcement is in effect, and
  a short "show at least one patch note" hint while the button is disabled.
- **The users' history read also refreshes on the administrator's own
  changes** (it shares the announcements cache tag), so "What's new" shows an
  edit without a reload. The gate therefore decides on the first read only: an
  announcement made during a page view opens at the next load, for the
  administrator as for everyone.
- **Locale fallback** stays the shipped resolver (viewer's language, then
  English, then any language filled in), so a French-only note is shown to an
  English viewer rather than left out as the delta spec words it; only a note
  with no text at all is left out.
- **A failed "seen" record is silent**, as the spec requires; the former error
  toast and its key are removed.
- **Not in the plan**: each card has a line saying whether users can read it;
  the dialog body keeps a minimum height while navigable so the arrows stay
  put; an arrow reaching its end hands the focus to the other one; the history
  filters gained `unannounced` beside `announced`; `drag_indicator` joins the
  supported icon list; `RowControls` moved to its own file, shared by both
  lists; patch notes have their own delete confirmation wording.
- **Help Center**: only `getting-started/first-steps.md` is updated (owner
  instruction); task 8.1 stays open.
- **Tests**: happy-dom has no layout, so a pointer drag and the keyboard
  sensor's moves cannot run there. The list tests drive the drop through the
  drag-and-drop context's callbacks and check the sensors and spoken texts;
  the real gestures belong to the manual check (task 9.2).

## Open Questions

- None left: the drag-and-drop question is closed (library, see above).
