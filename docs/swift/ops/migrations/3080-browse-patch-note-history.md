---
schema: 1
title: "Announce patch notes as a package and show the history by exposure"
impact: minor
after: [add-patch-note-announcements, 3061-platform-admission-and-link-joiners]
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

Deploy the control-plane backend and the frontend together. Two control-plane
Alembic revisions run with the normal migration step; no backfill or manual
step is needed.

`e5ff6d80cc9f` (parent `9f6d3c2a1b08`):

- drops the index that allowed a single enabled patch note;
- adds `platform_announcement.position` and numbers the existing patch notes,
  most recently created first;
- drops `platform_announcement_dismissal` and creates
  `platform_announcement_seen` (one row per user).

`a6c1d94e27b3` (parent `e5ff6d80cc9f`):

- creates `platform_announcement_exposure` and converts the activation
  history into it, one line per exposure: each banner activation is paired
  with the deactivation that followed it;
- turns the patch note that was enabled into the first announced package;
- drops `platform_announcement_activation_event`.

What administrators and users see afterwards:

- users keep reading the patch note that was enabled, from **What's new**; no
  patch-note dialog opens for anyone until an administrator uses **Announce
  the update**;
- the Patch notes tab is a working area: its toggles choose what the next
  announcement includes, and nothing done there reaches users before that;
- earlier "Don't show again" choices are discarded: that option no longer
  exists;
- in the history, patch-note lines from before the upgrade show their dates
  but cannot be opened: their content of the time was not kept.

## Validation

As a platform admin, open **Administration → Announcements → Patch notes**,
turn on two patch notes and reload as another user: no dialog opens, and
**What's new** still shows the earlier patch note. Use **Announce the update**
and reload as that user: the dialog opens once, on the first of the two. Edit
one of them: users still read the announced text. In the history, the
announcement is one line that opens the package as users saw it.

## Rollback

Use the normal rollback procedure. Downgrading `a6c1d94e27b3` rebuilds the
activation events from the history lines and loses the announced packages and
who ended an exposure. Downgrading `e5ff6d80cc9f` keeps the topmost enabled
patch note enabled and disables the others, and drops what users have seen;
the earlier "Don't show again" choices are not restored.

## Limitations

An announced package cannot be edited: correcting a typo means editing the
patch note and announcing again, which shows the dialog to every user once
more. An announcement holds at most 10 patch notes. **Withdraw the current announcement** leaves **What's new** empty until
the next announcement.
