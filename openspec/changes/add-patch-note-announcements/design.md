## Context

See proposal.md for the motivation. This section describes what exists today.

**Control-plane backend.** Announcements shipped with #2805 (archived change
`2026-09-25-add-platform-announcements`, capability spec
`openspec/specs/platform-announcements`, contract section 55 of
`CONTROL-PLANE-PRODUCT-CONTRACT.md`).

- `models/announcement_models.py`: one table, `platform_announcement` (Alembic
  `b88202b8451e`). Columns: `id` (uuid string), `severity`, `title`,
  `description_short`, `description_long` (each a JSON locale map),
  `enabled`, `dismissible`, `content_version`, `created_at/updated_at`,
  `created_by/updated_by` (uids). Limits: title 200, short 500, long 20,000
  characters per locale.
- `announcements/store.py`: `AnnouncementStore`, pure CRUD. Every method takes
  an optional `session`; without one it opens its own auto-committed
  transaction (`fred_core.sql.use_session`). The service never shares a
  session across calls today.
- `announcements/service.py`: every admin operation checks
  `OrganizationPermission.CAN_MANAGE_PLATFORM` inline, and emits
  `platform.announcement.{created,updated,toggled,deleted}` audit records.
  `content_version` bumps on reader-visible edits and on an off-to-on toggle.
  The content `PUT` never changes `enabled`; only `PUT .../enabled` does.
- `announcements/api.py`: `GET /announcements/active` (authenticated only) and
  admin `GET/POST /admin/platform/announcements`,
  `PUT/DELETE /admin/platform/announcements/{id}`,
  `PUT /admin/platform/announcements/{id}/enabled`.
  All are listed in `docs/swift/platform/authz-endpoint-matrix.yaml`, which
  `tests/test_authz_endpoint_matrix.py` checks against the registered routes.
- Tests: `tests/test_announcements.py` (service, validation, authz, audit) and
  `tests/test_announcement_store.py`, on SQLite.
- Not part of platform export/import.
- Current Alembic head: `aac66348e27b` (user avatar key).

**Frontend.**

- Admin page `/admin/annonces` (`components/pages/admin/AnnouncementsPage/`):
  each row renders the real `AnnouncementBanner` in preview mode, plus an
  enable `Switch`, an Edit `IconButton` and a `DeleteIconButton` behind a
  `ConfirmationDialog`. The header "Create" button is hidden when the list is
  empty; the `PageEmptyState` carries the action instead.
- `AnnouncementEditorDialog`: the shared `Dialog` (max width 880) with a fr/en
  locale `ButtonGroup`, severity, dismissible switch, and plain `TextArea`s.
  Banners are bilingual: every text is a `{fr, en}` map resolved by
  `features/announcements/announcementText.ts` with an `en` fallback.
- Users: `features/announcements/AnnouncementStack.tsx`, mounted in `App.tsx`
  inside `GcuGuard` and `BootstrapGuard`, so only after sign-in, terms
  acceptance and bootstrap. It polls `GET /announcements/active` (shared
  `crossSessionRefreshOptions`, plus refetch on focus). Banner dismissal is
  per browser in `localStorage`, keyed by id and `content_version`, in
  `announcementDismissal.ts` with try/catch guards.
- Generated hooks are aliased in `slices/controlPlane/controlPlaneApiEnhancements.ts`
  (`useActiveAnnouncementsQuery`, `useAnnouncementsQuery`, ...), sharing one
  `ControlPlaneAnnouncement` `LIST` tag.
- i18n keys live under `rework.announcements.*` in `locales/{fr,en}/translation.json`.
- Help Center (`features/helpCenter/content/{fr,en}/`): no page mentions
  announcements yet. `features/administration.md` is the admin page;
  `getting-started/first-steps.md` is the closest user page.
- `docs/swift/ux/COMPONENT-UX.md` has no announcements section yet.

**Reusable pieces found.**

- Markdown rendering: `shared/molecules/MarkdownRenderer` (the chat renderer;
  sanitized, `fullWidth` prop). `MarkdownPreviewModal` wraps it in a
  `FullPageModal`, but has no footer.
- Markdown editing: `shared/molecules/PromptEditor` (CodeMirror, markdown
  mode, `rows` prop, plain text in and out). Already used for a large markdown
  field on `PlatformPromptPage`. `ProseMdxEditor` is a WYSIWYG used by the
  team wiki; it round-trips through an AST, which we do not want here.
- Dialogs: `shared/molecules/Dialog` (title, scrollable body, footer with an
  optional cancel and one confirm button, `maxWidth`). It is packaged in
  `@fred-oss/ui`, so its props reach external teams. `Checkbox` atom exists.
- User names: `GET /users/by-ids` (any authenticated user, up to 100 ids)
  aliased as `useUsersByIdsQuery`, and `core/utils/userDisplayName.ts`.
- The current user is known once `BootstrapGuard` has resolved; anything
  mounted inside it runs after sign-in.
- `ReleaseNotesPage` renders the deployment's static `release.md`. It is a
  separate, deploy-time document; patch notes do not replace it.

## Goals / Non-Goals

**Goals:**

- Add the `patch_note` type with the smallest change to the existing model,
  service and page.
- Make "one active patch note" and "history in the same transaction" hold in
  the database, not only in the service.

**Non-Goals:**

- Scheduling (start/end dates), per-team targeting, read receipts or
  analytics on who saw a patch note.
- Server-side dismissal for banners: banners keep their per-browser
  dismissal.
- Pagination of the history, and any history for content edits (audit logs
  already cover edits).
- Changing `ReleaseNotesPage` or the deployment `release.md`.
- Including announcements in platform export/import.

## Decisions

### D1. A `kind` column on the existing table, body in `description_long`

Add `kind` (`String(16)`, not null, server default `'banner'`) to
`platform_announcement`. A patch note stores its markdown in
`description_long`; `title` and `description_short` are stored empty;
`severity` is stored as `info` and `dismissible` as `true` (the server forces
both). `AnnouncementWriteRequest` gains `kind: Literal["banner", "patch_note"]
= "banner"`, so existing clients keep working. A model validator applies the
per-kind rules: a banner needs title and short text, a patch note needs a body
(same 20,000 limit). `update` refuses a `kind` different from the stored one
(422).

Why: `description_long` already means "markdown shown in a dialog", with the
right length limit. Reusing it avoids a column, keeps one `Announcement`
schema, one list query and one RTK tag. The `Field` description says what it
holds for each kind.

Alternatives: a separate `platform_patch_note` table with its own routes
(duplicates CRUD, toggle, audit and page plumbing); a new `body` column
(clearer name, but one more column that is empty for every banner);
a discriminated-union API schema (cleaner types, but a breaking change to the
generated client for no user benefit).

### D2. Bilingual body

Banners are bilingual (`{fr, en}` maps with `en` fallback), so patch notes are
too: one markdown body per locale, edited with the same locale switch, and a
title in exactly the same locales (so the title and the body a viewer gets
always come from the same language).

### D3. One active patch note: service rule plus partial unique index

`set_announcement_enabled` and `create_announcement` (when created enabled)
run in one transaction: disable any other enabled patch note, enable the
target, append the history events. In addition, a partial unique index
`uq_platform_announcement_active_patch_note` on `(kind)` where
`enabled AND kind = 'patch_note'` (declared with both `postgresql_where` and
`sqlite_where`) makes two enabled patch notes impossible even under
concurrent requests. A violation is mapped to `409 Conflict`; the admin
retries.

Why: the service rule gives the expected behaviour; the index makes it hold
under concurrency without locks.

Alternative: `SELECT ... FOR UPDATE` on the active row (does not cover the
"none active yet" race; SQLite does not support it).

### D4. One transaction across store calls

`AnnouncementStore` gains `transaction()`, an async context manager that
yields a session from its own factory (`use_session(self._sessions)`). The
service passes that session to the existing store methods and to the new ones
(`disable_other_patch_notes`, `append_activation_events`,
`list_activation_events`, `add_dismissal`, `is_dismissed`,
`count_dismissals`, `delete_dismissals`). The store stays
pure CRUD; the rules (who gets disabled, when an event is written) stay in the
service.

Alternative: put the rules inside `AnnouncementStore.set_enabled`, which
breaks the store's documented "never decides" split.

### D5. Activation history table

`platform_announcement_activation_event`: `id` (uuid string), `announcement_id`
(string, **no** foreign key, so events outlive the announcement), `kind`,
`label` (JSON locale map: the title, taken at event time), `action` (`activated` | `deactivated`), `actor_uid`
(nullable string), `occurred_at` (timestamptz), index on `occurred_at`.
Append-only: the store has no update or delete method for it.

Events are written only when `enabled` actually changes: off-to-on toggle,
on-to-off toggle, creation in the enabled state, automatic disable of the
previous patch note (actor = the admin who enabled the new one), and deletion
of an enabled announcement (recorded as `deactivated`). Re-sending the same
state writes nothing.

`GET /admin/platform/announcements/activation-history` returns the 100 newest
events, no pagination. Why 100: activations are rare manual actions (a few a
week), so 100 covers months; and 100 is the `GET /users/by-ids` limit, so the
page resolves every actor name in one call. Pagination can be added later
without changing the stored data.

The API returns `actor_uid`; the frontend resolves display names with
`useUsersByIdsQuery` and `userDisplayName`, falling back to the uid (for
example after the user was deleted). No name or email is written to logs or to
this table.

### D6. Dismissal table and delivery routes

`platform_announcement_dismissal`: `announcement_id` (FK to
`platform_announcement.id`, `ON DELETE CASCADE`), `user_id`, `dismissed_at`;
primary key `(announcement_id, user_id)`. The store also deletes dismissals
explicitly when deleting an announcement, since SQLite tests do not enforce
foreign keys. `DELETE /users/{id}` removes the user's dismissals next to
`delete_favorites_for_user`.

Routes (both authenticated only, identity from the token):

- `GET /announcements/patch-note` returns `ActivePatchNote { patch_note:
  Announcement | null, dismissed: bool }`: the enabled patch note (`null` when
  none) and whether the caller has a dismissal row for it, so the profile
  menu can reopen a dismissed note.
- `PUT /announcements/{announcement_id}/dismissal` upserts the caller's
  dismissal; `204`, idempotent; `404` when the id is
  not a patch note.

`GET /announcements/active` filters on `kind = 'banner'`, so
`AnnouncementStack` needs no change.

Why a separate read: it is per user (it reads the dismissal table), it is read
once per load instead of every minute, and it keeps the polled banner route
identical for everyone.

### D7. When a dismissed patch note is shown again

Product decision: editing a note while it stays enabled does not re-show it
(typo fixes); every off-to-on toggle re-shows it to everyone, including users
who dismissed it, the same as a banner relaunch.

Design: every off-to-on toggle of a patch note deletes all its dismissal rows
in the same transaction as the enable, after the row lock; a row present means
hidden. For a patch note, `content_version` does not move on a content edit;
every off-to-on toggle bumps it, banner or patch note. Banners also bump on a
content edit. The client's per-sign-in "closed" flag includes the version, so
a re-shown note is not hidden by it.

Decision change (2026-10-09, later): dismissals first stored the note's
version and stale ones were ignored. The owner chose deleting them on
re-enable instead, so stale rows never stay in the database; the dismissal's
`content_version` column was dropped (migration edited in place).

Decision change (2026-10-09): the review round first re-showed a note only
when its title or body was edited while disabled (an `edited_while_inactive`
flag). The product owner then chose "any re-enable resets"; the flag and its
column were deleted.

### D8. Load-time dialog in the client

`features/announcements/PatchNoteGate.tsx` is mounted in `App.tsx` next to
`AnnouncementStack` (inside the guards). It queries `GET /announcements/patch-note`
once, without polling or refetch on focus: a patch note activated during a
session is seen at the next load. If a note is returned and the "closed" flag
is not set for this user and this sign-in, it opens `PatchNoteDialog`.

The flag is `localStorage["fred.patchNote.closed.<userId>.<loginSessionId>.<id>"]`,
where the login session is the access token's `sid` claim (else
`session_state`). Keyed by sign-in, every tab of one sign-in shares it and the
note comes back at the next sign-in; keyed by user, it never leaks to another
account on the same browser. Without a login-session id (insecure dev mode),
it falls back to `sessionStorage["fred.patchNote.closed.<userId>.<id>"]`, i.e.
once per tab. Writing a flag removes the same user's flags from other
sign-ins, so at most one sign-in's flags per user stay stored.

On Close, Escape or a scrim click: if the box is ticked, it calls the
dismissal mutation (a failure shows an error toast; the dialog still closes);
in all cases it sets the flag. Every storage access is wrapped in try/catch;
on error the dialog behaves as if nothing was stored. The flag is set on
close, not on open, so a reload while the dialog is still open shows it again.

### D9. One dialog component for users and admin preview

`shared/molecules/PatchNoteDialog` renders the shared `Dialog` (title "What's
new" / "Nouveautés", `maxWidth` 880, `hideCancel`, confirm label "Close") with
`MarkdownRenderer` (`fullWidth`) for the body. (Superseded on 2026-10-09:
`maxWidth` 720, and the header shows the patch note's title; see the
"Patch-note title" notes below.) The "Don't show again" checkbox sits in the
`Dialog` action bar, right before Close, through the `actionsAddon` prop
(superseded the first design, a sticky row at the end of the body; see the
2026-10-09 notes below). Its props are `title`, `markdown`, `open`, and
`onClose(dontShowAgain: boolean)`. The gate and the admin preview both use it;
the admin passes an `onClose` that ignores the checkbox, so a preview never
records anything.

Why: one component is what guarantees "preview equals user dialog". The
action-bar slot was first rejected (`Dialog` ships in `@fred-oss/ui`), then
adopted when the sticky row turned out to scroll the note on open.

The "release notes" look comes from typography, not a new design system: a
neutral `surface-container` band behind the first heading, `MarkdownRenderer`
defaults for lists and code, tokens only.

### D10. Admin page changes

- Header: two buttons, "New banner" and "New patch note", always shown; the
  empty state keeps its message without its own action, so the two buttons are
  not shown twice.
- Patch-note row (`PatchNoteRow`, local to the page): neutral
  `surface-container` card with an outline border, a `new_releases` icon, a
  "Patch note" label, the title; then the same `Switch`, a Preview
  `IconButton` (`visibility`), Edit and `DeleteIconButton`. Banner rows do not
  change.
- `PatchNoteEditorDialog` (local to the page): `Dialog` at `maxWidth` 1200
  with the fr/en `ButtonGroup`, a `PromptEditor` (about 24 rows) and an inline
  `MarkdownRenderer` preview side by side (stacked below 900 px), and a
  "Preview as users see it" button that opens `PatchNoteDialog` with the
  current locale's unsaved body. The existing `AnnouncementEditorDialog` stays
  for banners.
- `ActivationHistoryCard` (local to the page): right column on wide screens,
  below the list on narrow ones. Each entry shows the label in the viewer's
  locale (fallback `en`), a type label, "activated"/"deactivated", the date and
  time (`toLocaleString` in the viewer's locale), and the actor name. It
  refetches when the `ControlPlaneAnnouncement` `LIST` tag is invalidated.
- The count in the subtitle counts live banners only ("N bandeaux affichés à
  tous les utilisateurs"): an active patch note is not shown to every user,
  since some dismissed it (review fix).

## Risks / Trade-offs

- [`description_long` means "body" for patch notes] → documented on the column
  comment, the schema `Field` and contract section; one helper on each side
  reads it.
- [Unique-index conflict under concurrent activation returns 409] → rare,
  admin-only; the toast shows the error and the list refreshes.
- [A patch note activated mid-session is only seen at the next load] →
  intended; documented in the Help Center.
- [History capped at 100] → older events stay in the table and in audit logs;
  pagination can be added later.
- [Actor uid kept after user deletion] → it is an opaque id, not PII; the card
  shows the uid when the name cannot be resolved.

## Migration Plan

1. One Alembic revision, `down_revision = "aac66348e27b"` (re-parent on the
   current `swift` head before merge): add `kind` with server default
   `'banner'` (backfills existing rows), the partial unique index, and the two
   tables. `downgrade` drops them.
2. Deploy backend and frontend together (minor impact: new tables, no
   configuration).
3. Rollback: downgrade the revision, which deletes patch notes (they would
   otherwise come back as broken banners) and drops the new columns,
   dismissals and history, then redeploy the previous version.

## Implementation notes (group A, 2026-10-09)

Small precisions made while implementing; none changes a requirement.

- `AnnouncementWriteRequest` keeps `severity`, `title` and `description_short`
  required (the generated banner type does not change); a patch-note payload
  sends placeholders, which the validator normalizes.
- Events written in one transaction (auto-deactivation, then activation) get
  strictly increasing `occurred_at` (+1 µs on a tie), so the history order is
  deterministic.
- `disable_other_patch_notes` takes `updated_by` and flushes before the target
  is enabled, so the partial index never sees two enabled rows in one flush.
- Audit: `.created` and `.toggled` carry `auto_disabled_ids`; `.deleted`
  carries `was_enabled`. Dismissals emit no audit record (user action, not admin).
- `DELETE /users/{id}` removes dismissals on the identity-provider path only,
  like prompt favorites; the local-directory path only suspends the account.
- Extra test: `tests/test_patch_note_announcement_migration.py` (backfill to
  `banner`, partial index, downgrade).

## Implementation notes (group B, 2026-10-09)

Small precisions made while implementing the admin page; none changes a
requirement.

- Row icon buttons, Preview included, stay `size="small"`, like the banner
  rows' Edit and Delete, so every row's controls have one size (task 4.3
  originally said `medium`). Preview sits before the switch, so the
  switch, Edit and Delete line up with the banner rows.
- `PatchNoteEditorDialog` hides its own `Dialog` while "Preview as users see
  it" is open instead of stacking two: both `Dialog`s listen to Escape and Tab
  on `window`, so stacked they would both close and fight over the focus trap.
  The typed text lives in the editor's state and is still there on return.
  `Dialog` is unchanged.
- `PromptEditor` has no `onBlur` or `maxLength`: the "body required" error
  shows after a `focusout` on its wrapper, and the 20,000-character limit is a
  counter plus an error that disables Save.
- `PatchNoteDialog`'s checkbox row is a sticky row at the end of the body
  (D9). Its negative margins cancel the `Dialog` body padding so it spans edge
  to edge right above the action bar. No headless screenshot was taken (the
  app needs a Keycloak sign-in); the visual check stays with task 6.3.
- A failed toggle needs no explicit refetch: RTK Query invalidates the
  mutation's static `LIST` tag on a rejected call too, so the list always
  shows the server's state.
- The empty state's text now mentions both types; the `page.create` key is
  replaced by `page.createBanner` and `page.createPatchNote`. "New banner" is
  the filled button, "New patch note" the outlined one.
- History entries: type as a neutral `StatusBadge`, `visibility` /
  `visibility_off` marker, date via `toLocaleString(locale, {dateStyle:
  "medium", timeStyle: "short"})`. An event with no actor shows "unknown
  author".
- Component tests use key-echo `t` mocks like the rest of the page's tests.
  fr/en parity is checked with the `jq` diff of task 5.5, and
  `PatchNoteDialog.test.tsx` checks its strings exist in both files.
- Under 600 px the row controls wrap below the banner or card.

## Implementation notes (group C, 2026-10-09)

Small precisions made while implementing the user dialog; none changes a
requirement.

- `PatchNoteGate` sits inside `ToastProvider`, as the router's sibling, rather
  than literally next to `AnnouncementStack`: the error toast needs that
  provider. It stays inside `GcuGuard`/`BootstrapGuard` and above the router,
  so it never shows on those screens and never remounts on navigation. Both
  guards replace the app instead of overlaying it, so no other startup modal
  can be open under it.
- The closed id is also held in React state, so failing storage
  cannot reopen the dialog on a rerender. A failed dismissal shows the
  `patchNote.dismissFailed` toast and logs nothing.
- The body uses `resolveAnnouncementText` (viewer's locale, then `en`, then any
  filled locale), like banners. A note with no body in any locale opens nothing.
- Help Center: the user section is in `getting-started/first-steps.md`
  ("Nouveautés" window), the admin section in `features/administration.md`.
  Pages are discovered from the files, so no registry changed.
- COMPONENT-UX: the existing announcements section was extended instead of
  adding a second one.

## Product-owner follow-up (2026-10-09)

Supersedes D10's header and history-column bullets.

- One "New announcement" button opens a type chooser (shared `Dialog`, two
  `SelectableCard` tiles). A tile opens its editor immediately: the type is
  the only question, so a confirm button would only add a click. The Dialog's
  single action is "Cancel". `SelectableCard` gained an optional `icon`
  (Material Symbols name, package-safe) and an optional `selected`; both are
  additive for `@fred-oss/ui` consumers.
- The history is a `CollapsibleSidePanel`, extracted from the resources page's
  `ImportPanel` rather than copied, so both panels share one rail, toggle,
  width range and resize behaviour. It follows the import panel's defaults:
  collapsed, state not remembered, only the open width persists. It stays
  beside the list at every width (the panel's own 45vw cap), replacing the
  former below-the-list layout under 1100 px.
  `ActivationHistoryCard` became `ActivationHistory`: the panel now carries
  the surface and the title, so the component is just the list.
- Page padding drops from L/XL to `--spacing-m`, in the page module only.

## History as a view (2026-10-09)

Supersedes the side-panel bullet above.

- The page gets a top-level view switch (`ButtonGroup` tabs in the
  `PageHeader` `tabs` slot): "Announcements", the list, and "History". A side
  panel squeezed the history into a column; as a view it takes the whole body,
  so it is the shared `LocalizedDataTable` with one column per field (label,
  type, action, date and time, author), at its dense `size="small"` preset.
  The table's own client-side sort is enabled on every column; the default
  order stays the API's newest first.
- The Type chip of a banner takes its severity tone (`StatusBadge` tones are
  the banner's severity roles). Events gain a nullable `severity` snapshot,
  taken at event time, `null` for patch notes, whose stored severity is a
  placeholder. Migration `cb6f39c6d80c` was edited in place since it is
  unpublished; rows written before stay `null` and render neutral.
- The create button shows on the Announcements view only: the history has
  nothing to create. The selected view is plain state, not in the URL or in
  storage, like every other admin page.
- The `CollapsibleSidePanel` extraction is reverted (`ImportPanel` back to its
  `swift` state, the molecule deleted): it no longer had a second user.

## Review fixes (2026-10-09)

- Escape and the scrim report the checkbox state like Close, so a ticked box
  always records the dismissal (the spec requirement; the first version
  dropped it on Escape).
- The "closed" flag moved from a per-tab `sessionStorage` key to a per-user,
  per-sign-in `localStorage` key (D8).
- The content `PUT` no longer writes `enabled` at all: `store.update` lost its
  `enabled` parameter, so a toggle landing between the service's read and its
  write is not undone by a stale value.
- `store.add_dismissal` swallows an `IntegrityError` only when the dismissal
  now exists (a concurrent duplicate); a foreign-key failure (note deleted
  meanwhile) re-raises and the service returns 404.
- Editor counters format numbers with the UI language (`Intl.NumberFormat`),
  the history card's heading id comes from `useId`, and the fr label of
  "Preview as users see it" is "Aperçu côté utilisateurs".

## Open Questions

- Should the history table also offer pagination ("show older") later? Not
  needed for the first version; the API can gain `before`/`limit` without a
  schema change.

## Implementation notes (patch-note title, 2026-10-09)

Product-owner follow-up after testing; it changes the requirement on patch-note
titles (spec updated).

- A patch note now has a plain-text title per locale, stored in the existing
  `title` map: no new column, no migration. The validator cleans and requires
  it exactly like a banner's (blank locales dropped, one locale minimum, 200
  characters); only `description_short` stays normalized to `{}`. The banner
  rule has no newline check (the field is a single-line input), so neither
  does the patch-note one.
- The history label is the title per locale (the body-headline fallback was
  deleted in the review round: no untitled patch note was ever released).
- The editor puts a `TextInput` (the banner editor's atom, `maxLength` 200)
  under the locale `ButtonGroup`, above the body. `PatchNoteDialog` takes the
  resolved `title` and shows it as the `Dialog` title; the gate, the profile
  menu, the row preview and the editor preview pass it.
- `PatchNoteDialog` is 720 px wide (was 880).
- The body placeholder is a single line: CodeMirror rendered the multi-line one
  as one tall box and misplaced the caret. The `PromptEditor` CSS workaround is
  reverted, so that component matches `swift` again.

## Implementation notes (dialog opens at the top, 2026-10-09)

- Root cause of the note opening scrolled halfway down: the `Dialog` focuses
  its first focusable element on open. With no link in the note, that was the
  sticky checkbox, whose place in the flow is the end of the body, so the
  browser scrolled the body down to it.
- Fix by moving the checkbox out of the body: `DialogPrimitive` gains an
  optional `actionsAddon` (additive in `@fred-oss/ui`), rendered in the action
  bar before the buttons, `--spacing-m` from them. Focus order is checkbox,
  then Close. The sticky row and its CSS are deleted.
- A link or code-block button in the body was still the first focusable
  element; fixed in the review round by `initialFocus="dialog"` (below).
- Product-owner follow-up: the dialog's header gets a bottom border and its
  action bar's top border moves from `outline-muted` to `outline-variant`.
  Both belong to `Dialog`, so it gains an opt-in `dividers` prop (additive in
  `@fred-oss/ui`) rather than `:global` overrides from `PatchNoteDialog`.

## Implementation notes (review round, 2026-10-09)

Two independent reviews; the product owner decided each point.

- Concurrency: toggle, content update and delete read the row with
  `store.get(for_update=True)` (`SELECT ... FOR UPDATE`, a no-op on SQLite),
  so two concurrent toggles or deletes cannot both record an event. The
  content update joined a transaction for the same lock, because the new
  `content_version` is computed from the stored one.
- Migration `cb6f39c6d80c` (unreleased, edited in place): its
  downgrade deletes patch notes before dropping `kind`, so the manual
  "delete patch notes first" rollback step is gone.
- Title and body locales must match (validator); with that, the headline
  fallback (backend `patch_note_headline`/`label_for`, frontend
  `patchNoteHeadline`) and the dialog's generic "What's new" title were
  unreachable and are deleted.
- Admin list: `AdminAnnouncement` adds `dismissal_count` (one grouped `COUNT`
  over the dismissal rows). A separate response model keeps the count
  off user-facing payloads.
- Dialog: `DialogPrimitive` gains opt-in `initialFocus="dialog"` (the dialog
  node takes focus, so the note opens at its top and screen readers start
  from the title) and `hideConfirm` (the type chooser's only action becomes a
  text Cancel). `MarkdownRenderer` gains opt-in `linksInNewTab`. All additive
  in `@fred-oss/ui`.
- `PatchNoteBody` (in the `PatchNoteDialog` folder) holds the markdown and its
  release-notes CSS; the dialog and the editor's inline preview both use it.
- Reopening: `useActivePatchNote` resolves the note once for the gate and for
  `UserProfile`, which adds "Nouveautés" / "What's new" and its own
  `PatchNoteDialog` without the checkbox. Same cached query, no extra request.
- Editor: Escape, scrim and Cancel go through `onCancel`, which asks via
  `ConfirmationDialog` when title or body differ from what was saved; no new
  `Dialog` prop was needed. Confirmations replace the editor dialog while
  open (as the preview does) instead of stacking. "Save and activate"
  (outlined, `actionsAddon`) on an inactive note saves then toggles; enabling
  while another note is active, from the list or the editor, first confirms
  and names that note. The save toast says whether the note is live.
- Nits: the remembered history filter is validated; the chip group is named;
  "Unknown author" is capitalised; the editor opens on the first language
  with content.
- Deferred: writing helpers (insert a New / Improved / Fixed template, copy
  FR to EN to start a translation), drafted as a follow-up issue.
