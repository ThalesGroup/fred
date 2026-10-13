## Why

Patch notes and banners are managed in one mixed admin list, only one patch
note can be active, and a user can read nothing but that one (issue #3080,
follow-up to #3016). Activating a note is also what pushes it at sign-in, so
an administrator cannot prepare, correct or reorganise notes without thinking
about who will be interrupted. This change makes the patch notes a working
area, turns what users read into an announced, frozen package, and makes the
history show what users actually saw.

## What Changes

- **Admin page**: three tabs, "Banners" (the current "Announcements" tab
  renamed, banners only), "Patch notes" (new, second), then the history. Each
  tab creates its own kind, so the kind chooser goes away.
- **Working area**: creating, editing, reordering or toggling a patch note
  never reaches users. Each patch note has a toggle, off at creation, that
  decides whether it is included in the next announcement.
- **Manual order**: the administrator reorders the Patch notes list by drag
  and drop or by keyboard; an announcement takes the included notes in that
  order. No date-based ordering.
- **Announce button**: "Announce the update", behind a confirmation listing
  the included patch notes, freezes them (title and body, every language) as a
  package. Users read that package, and only that, until the next
  announcement, and every user gets the dialog once per announcement. The date
  of the announcement in effect and its author are shown next to the button;
  it is disabled when no patch note is included.
- **Withdraw**: "Withdraw the current announcement", behind a confirmation,
  leaves no package in effect: "What's new" is empty and no dialog opens until
  the next announcement.
- **User dialog**: one dialog at sign-in and from "What's new", showing the
  package in effect, with a navigation at the left of its action bar (icon
  button, "1 / 4" position, icon button), opening on position 1. No "Don't
  show again" checkbox. "What's new" is hidden when no package is in effect.
- **History**: one line per exposure instead of one per event: a banner
  activation, or a patch-note announcement, with its activation, its
  deactivation and its author. No action column; the filter is by type. A
  patch-note line keeps its package, which the administrator can open as users
  saw it. Toggling a patch note writes nothing.
- **BREAKING (internal API)**: `GET /announcements/patch-note` and
  `PUT /announcements/{id}/dismissal` are replaced by a package read and a
  per-announcement "seen" record; new admin routes for ordering, announcing,
  withdrawing and reading a package; the history response changes shape. The
  only consumer is the Fred frontend, regenerated in the same change.
- **Removed**: the "one active patch note at a time" rule with its unique
  index, its `409`, the automatic deactivation and its confirmation; the
  re-show on re-enable; the per-note dismissal table; the per-sign-in browser
  memory; the per-note count of users who hid it; the kind chooser; the
  activation events and their `action`.
- Banners are unchanged, apart from how their history is shown.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `platform-announcements`: patch notes go from "one active note, shown when
  activated, dismissible for good" to "a working area whose included notes are
  announced as a frozen package, browsed in one dialog"; the history goes from
  events to exposures.

## Impact

- **Prerequisite**: the delta is written against the patch-note requirements
  of `add-patch-note-announcements`, merged in PR #3022 but not archived yet.
  That change must be archived first so `openspec/specs/platform-announcements`
  holds the requirements this one modifies and removes.
- **Backend** (`apps/control-plane-backend`): `announcements/` (api, schemas,
  service, store), `models/announcement_models.py`, the user-deletion cleanup
  in `users/api.py`, two linear Alembic migrations (drop the unique index, add
  a position column, replace the dismissal table by a per-user marker; then
  replace the activation events by exposure lines holding the packages), tests.
- **Contract**: `openapi.json` and `controlPlaneOpenApi.ts` regenerated; dated
  entry in `CONTROL-PLANE-PRODUCT-CONTRACT.md` extending section 61.
- **Frontend** (`apps/frontend/src/rework`): `PatchNoteDialog`,
  `features/announcements/` (gate, read hook; `patchNoteSession.ts` deleted),
  `UserProfile`, `AnnouncementsPage` (tabs, reorderable list, announce button;
  `AnnouncementKindChooser` deleted), `PatchNoteEditorDialog`,
  `ActivationHistory`, fr/en locales. The frontend has no drag-and-drop
  library and no reorderable list component today; see design.md.
- **Docs**: Help Center fr+en (`features/administration.md`,
  `getting-started/first-steps.md`), `COMPONENT-UX.md`, a migration note under
  `docs/swift/ops/migrations/` (no operator action; `impact: minor` because
  of the Alembic revision).
- Not on a hot path: one read per application load, as today.
