## Why

Patch notes and banners are managed in one mixed admin list, only one patch
note can be active, and a user can read nothing but that one (issue #3080,
follow-up to #3016). Activating a note is also what pushes it at sign-in, so
an administrator cannot prepare, correct or reorganise notes without thinking
about who will be interrupted. This change separates three things that were
one: which patch notes users can read, in which order, and when they are
announced at sign-in.

## What Changes

- **Admin page**: three tabs, "Banners" (the current "Announcements" tab
  renamed, banners only), "Patch notes" (new, second), then the activation
  history. Each tab creates its own kind, so the kind chooser goes away.
- **Visibility toggle**: each patch note has a toggle that only decides
  whether it appears in the users' history. Any number can be visible. A new
  patch note is created with the toggle off. Patch notes stay editable
  whatever their age.
- **Manual order**: the administrator reorders the Patch notes list by drag
  and drop or by keyboard; that order is the order of the users' dialog
  (position 1 is the top of the list). No date-based ordering.
- **Announce button**: an "Announce the update" button on the Patch notes tab, behind a
  confirmation, announces the patch notes. From then on every user gets the
  dialog at their next sign-in, once per user per announcement. Nothing else
  opens it: not creating, editing, reordering or toggling. The date of its
  last use and the administrator who used it are shown next to it; it is
  disabled when no patch note is visible.
- **User dialog**: one dialog at sign-in and from "What's new", with a
  navigation at the left of its action bar (icon button, "1 / 4" position,
  icon button), opening on position 1. No "Don't show again" checkbox.
  "What's new" is hidden when no patch note is visible.
- **BREAKING (internal API)**: `GET /announcements/patch-note` and
  `PUT /announcements/{id}/dismissal` are replaced by a history read and a
  per-announcement "seen" record; new admin routes for ordering and
  announcing. The only consumer is the Fred frontend, regenerated in the same
  change.
- **Removed**: the "one active patch note at a time" rule with its unique
  index, its `409`, the automatic deactivation and its confirmation; the
  re-show on re-enable; the per-note dismissal table; the per-sign-in browser
  memory; the per-note count of users who hid it; the kind chooser.
- Banners are unchanged.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `platform-announcements`: patch notes go from "one active note, shown when
  activated, dismissible for good" to "a visible, manually ordered set browsed
  as a history, announced at sign-in on an explicit administrator action".

## Impact

- **Prerequisite**: the delta is written against the patch-note requirements
  of `add-patch-note-announcements`, merged in PR #3022 but not archived yet.
  That change must be archived first so `openspec/specs/platform-announcements`
  holds the requirements this one modifies and removes.
- **Backend** (`apps/control-plane-backend`): `announcements/` (api, schemas,
  service, store), `models/announcement_models.py`, the user-deletion cleanup
  in `users/api.py`, one Alembic migration (drop the unique index, add a
  position column, replace the dismissal table by a per-user marker), tests.
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
  `docs/swift/ops/migrations/` (no operator action: patch increment).
- Not on a hot path: one read per application load, as today.
