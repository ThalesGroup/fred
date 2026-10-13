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

- Three independent controls: inclusion in the next announcement (`enabled`),
  order (a position), announcement (an explicit action freezing a package).
- Users read a frozen package, never the live rows.
- One history line per exposure, the same table for banners and announcements.
- Remove more than is added: the one-active rule, the per-note dismissals, the
  browser memory, the kind chooser, the checkbox, the user count, the events.

**Non-Goals:**

- Scheduling an announcement, or announcing to a subset of users.
- A reusable drag-and-drop component for other pages.
- Any change to banners, their delivery, their dismissal or their editor.
- Writing helpers for the patch-note editor (#3017).

## Decisions

**1. Inclusion is `enabled`.** A patch note's `enabled` column keeps its
route, its switch and its audit records; it means "included in the next
announcement" and writes no history. The partial unique index goes, and with
it `disable_other_patch_notes`, the `409` branch, `auto_disabled_ids` and the
frontend confirmation naming the replaced note. A patch note's
`content_version` no longer keys anything; the shared toggle code that bumps
it is left alone. Alternative: a separate column. Rejected: two flags for one
decision.

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

**3. One table of exposures, which is also the history and the packages.**
`platform_announcement_exposure` replaces
`platform_announcement_activation_event`. One row per exposure: `id`, `kind`,
`announcement_id` (the banner; the first note for a package), `label` (title
per locale at the time), `severity` (banner), `actor_uid`, `activated_at`,
`deactivated_at` (null while it lasts), and for an announcement `note_count`
and `package`, a JSON list of `{id, title, description_long}` snapshots.
Enabling a banner inserts a row; disabling or deleting it sets
`deactivated_at`. Announcing ends every open patch-note row and inserts a new
one with its package, in one transaction; withdrawing only ends the open row.

The *announcement in effect* is the open patch-note row that holds a package.
That one definition feeds the users' read, the pending marker, the admin "last
announcement" read and the withdrawal, so they cannot disagree. The history is
a plain read of the table: nothing is derived or paired at read time. `package`
is a deferred column, so listing 100 lines does not load 100 packages.

Alternatives. A package table beside an events table, exposures derived by
pairing events at read time: rejected, two tables and a derivation for what
one row states directly, and "replaced" or "withdrawn" would need two more
event kinds. A package table beside the exposure table: rejected, a package
has exactly one line and no life of its own. Snapshot rows per note instead of
JSON: rejected, a package is only ever read whole. Trade-off: the table is no
longer append-only, since ending an exposure updates its row.

**4. "Seen" is one row per user, replacing the dismissal table.**
`platform_announcement_dismissal` (per user and note) is dropped and replaced
by `platform_announcement_seen`, keyed by `user_id` and holding the id of the
last announcement (exposure row) that user has seen and when. An announcement
is pending for a user when one is in effect, it opens the dialog (see the
migration plan for the one that does not) and the user's row does not name it.
Rows are removed with the user, where `delete_dismissals_for_user` was called.
The client records the id it was shown, not "the latest", so an announcement
made between the read and the close stays pending; the server ignores a record
that would move a user back to an older announcement. Alternative: a column on
a user table. Rejected: control-plane has no user table of its own to extend.

**5. Routes.** Replacing, not adding beside:

| Method | Path | Permission | Purpose |
| --- | --- | --- | --- |
| GET | `/announcements/patch-notes` | authenticated | `PatchNoteHistory { patch_notes: PatchNoteSnapshot[], pending_announcement_id: str \| null }`: the package in effect (empty when none) |
| PUT | `/announcements/patch-note-announcements/{id}/seen` | authenticated | `204`, idempotent; `404` when the id is not an announced package |
| PUT | `/admin/platform/announcements/patch-notes/order` | `can_manage_platform` | full ordered id list; `409` when stale |
| GET | `/admin/platform/announcements/patch-notes/announcement` | `can_manage_platform` | the announcement in effect (`id`, `announced_at`, `announced_by`) or null |
| POST | `/admin/platform/announcements/patch-notes/announcement` | `can_manage_platform` | announce; `409` when no patch note is included |
| DELETE | `/admin/platform/announcements/patch-notes/announcement` | `can_manage_platform` | withdraw, `204`; `404` when none is in effect |
| GET | `/admin/platform/announcements/patch-notes/announcements/{id}` | `can_manage_platform` | `PatchNoteSnapshot[]`: the package of a history line; `404` when the line is unknown or keeps none |
| GET | `/admin/platform/announcements/activation-history` | `can_manage_platform` | `AnnouncementExposure[]`, 100 newest first |

`AnnouncementExposure` is `{ id, kind, announcement_id, label, severity,
note_count, activated_at, deactivated_at, actor_uid }`. `note_count` is the
size of the package and null for a banner or a line without package, so it
also tells the client whether a package can be opened; the client formats
"first title + N others" from `label` and `note_count`.

Deleted: `GET /announcements/patch-note`, `ActivePatchNote`,
`PUT /announcements/{id}/dismissal`, `AdminAnnouncement.dismissal_count`
(the admin list returns `Announcement[]`, which gains `position`),
`AnnouncementActivationEvent` and `AnnouncementActivationAction`. The package
read stays once per application load, so "next sign-in" is in practice "next
load".

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
button sits in the Patch notes tab with its last-announcement text beside it,
uses the existing `ConfirmationDialog` listing the included patch notes, and
is disabled when none is included; the withdraw action sits beside it while an
announcement is in effect. The editor keeps its two saves, plain (toggle
untouched; off on create) and "save and include"; only `replacesTitle` and its
confirmation go. The history view filters by type and opens a line's package
in `PatchNoteDialog`.

## Risks / Trade-offs

- [The predecessor change was merged but not archived, so the main spec lacked
  the requirements this delta modifies] → `add-patch-note-announcements` is
  archived first, in its own commit (task 1.1).
- [Other open PRs add migrations on the same parent, `93427a5fe874`] → done
  once: `e5ff6d80cc9f` is re-parented onto `9f6d3c2a1b08`, the `swift` head
  after the merge of 2026-10-13, with no merge revision; to redo if `swift`
  gains another migration before this one lands (task 2.2).
- [Native drag and drop is weak on touch screens and gives plain visual
  feedback] → the admin page is a desktop surface and the keyboard path covers
  the rest; the library alternative is listed for the owner.
- [An administrator announces before ordering or toggling as intended] → the
  confirmation lists the included patch notes in their order; a mistake is
  fixed by announcing again or withdrawing.
- [Fixing a typo re-opens the dialog for everyone] → intended by the owner: an
  announcement is never replaced silently.
- [Two administrators announce at the same moment and leave two open rows] →
  the newest is the one in effect, and the next announcement or withdrawal
  ends every open patch-note row.
- [The exposure table is updated in place, so a wrong end time cannot be
  traced] → every change still emits its audit record.
- [A user created after the last announcement gets the dialog at first
  sign-in] → intended: it is new to them.
- [The package is loaded whole at every application load] → bounded by what
  the administrator announced; one indexed row.

## Migration Plan

Two linear Alembic migrations. The first is unchanged since it already ran on
a development database; the second sits on top of it.

`e5ff6d80cc9f`:

1. Drop `uq_platform_announcement_active_patch_note`.
2. Add `platform_announcement.position` and backfill patch notes, most
   recently created first.
3. Drop `platform_announcement_dismissal`; create the per-user table.

`a6c1d94e27b3`, exposures and packages:

1. Create `platform_announcement_exposure`.
2. Convert the events. Each `activated` event opens a line that the next
   `deactivated` event of the same announcement ends; the line keeps the
   opening event's id, title, severity, author and time. Patch-note
   activations become patch-note lines without package. `announced` events,
   which only a development database can hold, become lines without package
   too, ended by the next `announced` or `unannounced` event.
3. End every patch-note line still open, then, when at least one patch note is
   enabled, insert the first package from the enabled patch notes in position
   order, with `opens_dialog = false`.
4. Rename `platform_announcement_seen.announcement_event_id` to
   `announcement_id`; drop `platform_announcement_activation_event`.

`opens_dialog` is the one column that exists for the upgrade: "everybody
counted as having seen it" cannot be written as per-user rows, because users
who have not signed in yet have no row anywhere in this database. A package
with `opens_dialog = false` is in effect and readable, and pending for nobody.

No operator action, configuration or chart value; the migration note declares
`impact: minor`, which the migration-note check requires of any new Alembic
revision. Downgrading `a6c1d94e27b3` recreates the events table from the
lines (`activated`, and `deactivated` when ended; a package line becomes an
`announced` event, followed by `unannounced` when it was withdrawn and is the
newest), renames the column back and drops the exposure table; packages are
lost.

## Owner Decisions

Closed by the owner; written into the specs and tasks.

- Button label: "Annoncer la mise à jour" / "Announce the update", with the
  date of its last use and the administrator's name beside it.
- Arrows: left towards newer (position 1), right towards older.
- After upgrade: the currently enabled patch note becomes the first package,
  pending for nobody; its toggle stays on and the others are off.
- Per-note user counter: removed.
- One create button per tab; the kind chooser is removed.
- Drag handle at the left of each card; the order is also changeable by
  keyboard.
- Rework (final): an announcement is a frozen package of the included patch
  notes; the live list is a working area that never reaches users. Announcing
  always creates a new package and re-opens the dialog for everyone. A
  "Withdraw the current announcement" action leaves no package in effect.
- The earlier rule "hiding the last visible patch note cancels the
  announcement" and its `unannounced` event are removed.
- History is one line per exposure (banner activation, patch-note
  announcement) with activation, deactivation and author; no action, filter by
  type; a patch-note line keeps its package, openable by the administrator.

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
- The reorder route answers `204`; the per-user table is
  `platform_announcement_seen`.
- The first migration also updates the comment of the events table's `action`
  column; the second migration drops that table.
- New routes are listed in `docs/swift/platform/authz-endpoint-matrix.yaml`,
  which a backend test requires; the plan did not name that file.

## Divergences Of The Rework

- The history read is one table read, but `package` is a deferred column and
  each package is fetched by its own route, so a history of 100 lines stays
  small.
- The history route keeps its path (`.../activation-history`); only its
  response and operation name change (`list_exposure_history`).
- The seen route's parameter is `{announcement_id}`.
- A line records who started the exposure only; who ended it stays in the
  audit records.
- Banners enabled before the history existed have no line; disabling one ends
  nothing and writes nothing.
- Still open on the backend: a real `alembic upgrade head` on PostgreSQL (task
  2.2); both migrations are exercised on SQLite only.

## Frontend Divergences

Written before the rework to packages and exposures; the points about the
`announced` and `unannounced` history filters and about "What's new"
refreshing on the administrator's own edits no longer apply once section 10 of
tasks.md is done.

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
- **Help Center**: `getting-started/first-steps.md` is updated, and the
  platform-admin Announcements sections of `features/administration.md` are
  deleted in `fr` and `en` (owner instruction): they described the former
  behaviour and the Help Center documents the end-user side only.
- **Tests**: happy-dom has no layout, so a pointer drag and the keyboard
  sensor's moves cannot run there. The list tests drive the drop through the
  drag-and-drop context's callbacks and check the sensors and spoken texts;
  the real gestures belong to the manual check (task 9.2).

## Frontend Divergences Of The Rework

- **The withdraw explanation is the text of its confirmation**, not a tooltip
  on an info button: the critical `ConfirmationDialog` is the app's pattern
  for an action of that weight, and it cannot be missed.
- **The announce confirmation uses `ConfirmationDialog` directly**, for its
  `details` slot (the numbered list); the provider only carries a text.
- **The last-use line stays when nothing is included**: the announcement in
  effect is a frozen package and outlives the toggles. The "include at least
  one patch note" hint shows only when there is no last use to show.
- **"+ N others" counts from `note_count`** (N is `note_count - 1`); the line's
  title is the API's `label`, the first note's title.
- **The history filter is stored under a new browser key**, so a remembered
  action filter from the first version is simply ignored.
- **A package is fetched when its line's button is pressed**, not with the
  table; a failed read shows an error toast and opens nothing.
- **Toggle wording follows through**: the editor's second save reads "Save
  and include", and deleting a patch note says the current announcement is
  not changed.
- **Help Center**: the user page (`getting-started/first-steps.md`) already
  matches and is unchanged; no administrator content is added, and the former
  administrator sections stay deleted.
- The earlier point about "What's new" refreshing on the administrator's own
  changes now only concerns announcing and withdrawing; the gate still decides
  on the first read.

## Review Fixes

- **The confirmation is the contract.** The announce request carries the ids
  the confirmation listed, in order; the service compares them with the
  included patch notes inside the transaction and answers `409` on any
  difference. The page then reloads the list and says the selection changed.
  The action is also held while a toggle, a reorder or a list reload is under
  way, so the confirmation shows the settled order.
- **At most 10 patch notes per announcement**, one constant on each side
  (`MAX_PATCH_NOTES_PER_ANNOUNCEMENT`): `409` from the service, disabled
  action with a hint in the page. Patch-note id lists (order, announce) are
  bounded to 1000 by the schema (`422`), far above a real working list; the
  number of patch notes itself is not capped.
- **One lock for the writes that order or announce.** Announce, withdraw,
  create and reorder first take one transaction-scoped PostgreSQL advisory
  lock (the primitive `team_wiki` and the bootstrap already use). Two
  administrators can no longer leave two packages in effect, and a patch note
  created during a reorder no longer shares position 1. No schema change: a
  partial unique index would do the first part, but both migrations already
  ran on a development database. SQLite takes no lock (one writer at a time),
  so the offline tests check that the lock is taken, not the exclusion.
- **Seen is one statement.** `INSERT ... ON CONFLICT (user_id) DO UPDATE`,
  guarded so that it never replaces a record with an older announcement; when
  it writes nothing, a second read in the same transaction tells an unknown id
  (`404`) from a record already up to date. Same statement on both dialects.
- **Downgrade of `a6c1d94e27b3`**: the line the upgrade ended as it created
  its package is rebuilt as an activation only. It is recognized by its end
  time, equal to the package's start; when the upgrade found no enabled patch
  note there is no package to compare with and the deactivation is kept.
- **Not run**: the upsert, the advisory lock and both migrations on a real
  PostgreSQL; `libs/frontend/tests/validate-ui-archive.test.mjs`, which needs
  a full package build (the expected glyph count is 140, counted from
  `materialIcons`).

## Open Questions

- The drag-and-drop question is closed (library, see above).
- **Owner decision pending**: the cap of 10 patch notes per announcement. The
  mechanism is in place; only the number waits for confirmation.
