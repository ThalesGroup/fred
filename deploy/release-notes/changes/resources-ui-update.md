---
schema: 1
title: "Resources page: Corpus tree, stable table layout and copy name"
impact: none
configuration: none
configuration_reason: "Frontend-only change to the team resources page, its shared table and the import panel; no configuration key or default changes."
no_action_reason: "The tree reads the existing Control Plane folder entries API already used by the resources table; no new endpoint, permission or data migration is involved."
---
## Applicability

Weaver deployments using the team resources page or Knowledge Base document pages.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy the frontend normally. The **Corpus** folder tree is shown again beside
the resources table; each folder a user opens issues one paged
`GET /spaces/{id}/entries` request, the same request the table already makes.

## Validation

Open the resources page: the Corpus tree lists folders then files, opens down to
the folder shown in the table, and follows folder creation, renaming and
deletion. Resizing a column keeps the table width. Right-click a row and choose
**Copy name**. Finish an import: the import panel folds back once its last card
has gone.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

Text in file and folder names can no longer be selected with the mouse; use
**Copy name** instead.
