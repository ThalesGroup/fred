---
schema: 1
title: "Patch-note announcements and announcement activation history"
impact: minor
after: [user-profile-picture]
configuration: none
configuration_reason: "No configuration key, default or chart value changes; patch notes and their history live in the existing control-plane database."
---
## Applicability

All Fred deployments upgrading the control-plane backend and frontend.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy the control-plane backend and the frontend together. The control-plane
Alembic revision `cb6f39c6d80c` (parent `aac66348e27b`) runs with the normal
migration step:

- it adds the column `platform_announcement.kind`, with server default
  `'banner'`, so every existing announcement becomes a banner and renders as
  before;
- it adds a partial unique index allowing at most one enabled patch note;
- it creates `platform_announcement_dismissal` (per-user "Don't show again"
  choices, cleared whenever an admin enables the patch note again) and
  `platform_announcement_activation_event` (activation history).

No backfill or manual step is needed.

## Validation

As a platform admin, open **Administration → Announcements**, create a patch
note, preview it with **Preview as users see it**, then enable it: it appears
in the **History** view under your name. Reload the application as another
user: the patch-note dialog opens. Tick **Don't show again** and close it; it
does not open at the next load, and the profile menu's **What's new** entry
still reopens it. Existing banners still show as before.

## Rollback

With traffic paused and updated readers stopped, downgrade the control plane
to `aac66348e27b` and restart the previous images. The downgrade deletes every
patch note, then drops the new columns, the index, the dismissals and the
activation history.

## Limitations

- Announcements, dismissals and the activation history are not part of the
  platform export/import.
- A patch note enabled while a user has the application open is shown to that
  user at their next load, not immediately.
- The activation history page shows the 100 most recent events; older events
  stay in the database.
