## Why

Platform admins can only reach users through short banners. A new release needs a longer "what's new" note that every user sees once, at load, and that they can close for good. Admins also cannot tell who switched an announcement on or off, or when, because nothing records it.

Tracking: #3016

## What Changes

- **Two announcement types.** Every existing announcement becomes type `banner`, with no behaviour change. A new type, `patch_note`, carries a plain-text title and one Markdown body per locale (fr/en, like banners, in the same locales), with no severity or short description to author.
- **One active patch note at a time.** Activating a patch note deactivates the one that was active, in the same operation. Banners keep their current activation behaviour.
- **Patch-note dialog at load.** After sign-in, if a patch note is active and the user has not dismissed it for good, a large "What's new" dialog opens with the rendered Markdown, a "Don't show again" checkbox and a Close button.
  - Closing without the checkbox: the dialog comes back at the next app load, not on in-app navigation.
  - Closing with the checkbox: the dismissal is stored server-side for that user and that patch note, so it holds on every device.
  - A different patch note is shown again, even to users who dismissed earlier ones. Editing the active patch note does not show it again to users who dismissed it; disabling it, then enabling it again does.
  - The profile menu's "What's new" entry reopens the active patch note at any time.
- **Admin page.** Patch notes appear in the same list as banners, in a neutral style, showing their plain-text title (required, per locale, like a banner title). Each has the same activation switch as banners plus Preview, Edit and Delete. The editor has a large Markdown editor, an inline preview, and a button that opens the real user dialog.
- **Activation history.** A card on the announcements page lists every activation and deactivation of any announcement, newest first, capped at 100: which announcement (snapshot of the title, and type), when, and who. Events are written in the same transaction as the change and survive deleting the announcement.
- **API.** Existing routes gain a `kind` field (defaults to `banner`). `GET /announcements/active` returns banners only; the admin list adds each patch note's dismissal count. New: `GET /announcements/patch-note` (the active patch note and whether the caller dismissed it), `PUT /announcements/{id}/dismissal` (the caller's own dismissal), `GET /admin/platform/announcements/activation-history` (admin).
- **Storage.** One new column on `platform_announcement` and two new tables (dismissals, activation events), in one Alembic migration on the single head. Dismissals are removed when the announcement or the user is deleted.
- **Help Center and docs.** fr and en Help Center pages for administrators and users; product contract, authz matrix, COMPONENT-UX entry, and a `minor` migration note.

## Capabilities

### New Capabilities

None. Patch notes and the activation history extend the existing announcements capability.

### Modified Capabilities

- `platform-announcements`: announcements gain a type (`banner` or `patch_note`). Content rules, administration and delivery change for that type. New requirements cover the single active patch note, the load-time dialog and its dismissal, the admin preview, and the activation history.

## Impact

- **control-plane-backend**: `models/announcement_models.py`, `announcements/{schemas,store,service,api}.py`, one Alembic revision on head `aac66348e27b`, `users/api.py` (dismissals removed on user deletion), tests.
- **API contract**: three new routes and one new field on `Announcement` / `AnnouncementWriteRequest`; regenerated `controlPlaneOpenApi.ts`.
- **frontend**: `AnnouncementsPage` (list, create actions, history card), a new patch-note editor dialog and patch-note dialog, `App.tsx` (mount the dialog next to `AnnouncementStack`), `controlPlaneApiEnhancements.ts`, fr/en locales, Help Center content.
- **docs**: `CONTROL-PLANE-PRODUCT-CONTRACT.md` (new dated section), `authz-endpoint-matrix.yaml`, `COMPONENT-UX.md`, `docs/swift/ops/migrations/`.
- **Operations**: a database migration (minor impact). No configuration change.
