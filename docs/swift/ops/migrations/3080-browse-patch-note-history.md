---
schema: 1
title: "Browse the patch-note history and announce it explicitly"
impact: minor
after: [add-patch-note-announcements]
configuration: none
configuration_reason: "No configuration key, default or chart value changes; the order of patch notes and what each user has seen live in the existing control-plane database."
---
## Applicability

All Fred deployments upgrading the control-plane backend and frontend.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy the control-plane backend and the frontend together. The control-plane
Alembic revision `e5ff6d80cc9f` (parent `93427a5fe874`) runs with the normal
migration step; no backfill or manual step is needed:

- it drops the index that allowed a single enabled patch note;
- it adds `platform_announcement.position` and numbers the existing patch
  notes, most recently created first;
- it drops `platform_announcement_dismissal` and creates
  `platform_announcement_seen` (one row per user).

What administrators and users see afterwards:

- the patch note that was enabled stays the only one users can read; an
  administrator turns on the older ones to put them in the history;
- no patch-note dialog opens for anyone until an administrator uses
  **Announce the update**;
- earlier "Don't show again" choices are discarded: that option no longer
  exists.

## Validation

As a platform admin, open **Administration → Announcements → Patch notes**,
turn on two patch notes and reload as another user: no dialog opens, and the
profile menu's **What's new** shows both. Use **Announce the update** and
reload as that user: the dialog opens once, on the patch note at the top of
the list.

## Rollback

Use the normal rollback procedure. Downgrading the revision keeps the topmost
visible patch note enabled and disables the others, removes the announcement
events from the activation history, and drops what users have seen; the
earlier "Don't show again" choices are not restored.

## Limitations

Turning off or deleting the last visible patch note cancels the announcement
for users who had not seen it yet; an administrator announces again once a
patch note is visible.
