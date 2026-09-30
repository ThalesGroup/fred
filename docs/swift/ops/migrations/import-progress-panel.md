---
schema: 1
title: "Imports are followed in a panel, and survive the dialog closing"
impact: none
configuration: none
configuration_reason: "Frontend only: no configuration key, default, secret, permission or API contract changes."
no_action_reason: "No backend, database, API or permission change. The behaviour is unconditional and comes with the frontend bundle."
---
## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator action is required.

Behaviour change for users, requiring no operator action. Confirming an import
now closes the dialog immediately and the transfer carries on behind it, in a
panel beside the documents table on the team Resources page. The panel opens
itself when an import hands off, folds back into a rail, and can be resized.

Per file it distinguishes the transfer from the analysis, and only the ingestion
task's own success marks a document as ready — the end of the transfer no longer
does. A failed file stays listed with its cause put into the reader's language,
and can be sent again while the browser still holds it. A name taken by someone
else during the import is now asked as a question in the panel (**Replace** /
**Skip**) instead of ending the import with a notification telling the user to
start over. Files still queued can be cancelled before their request leaves.

The browser writes the names of files still in flight, and the folder they were
headed for, to `localStorage` under `fred.imports.unfinished`, striking each one
off as it reaches the server. This is what lets the panel name the files that
did not arrive after a tab was closed mid-import. It holds file names and
destination tag ids only — never file contents — and is cleared as soon as
nothing is outstanding.

## Validation

Import several files into a team folder: the dialog closes at once and the panel
lists every file from the start, showing the transfer and then the analysis.
Close the tab during a large import and reopen the Resources page: the panel
names the files that never arrived and offers to pick them again.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.
A leftover `fred.imports.unfinished` entry in a user's browser is ignored by the
previous frontend and is harmless.

## Limitations

Resuming an interrupted import requires the user to select the files again: a
browser cannot reopen a file it no longer holds. The same applies to retrying a
failed file and to answering a conflict after a reload — the panel says so
rather than offering an action that cannot work.

Cancellation covers files whose request has not left yet. A file already being
transferred is completed and ingested; stopping an analysis already under way is
a separate capability the server does not offer today.
