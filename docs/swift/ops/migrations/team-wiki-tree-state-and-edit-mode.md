---
schema: 1
title: "Team wiki remembers its tree and edits title, parent and deletion in edit mode"
impact: none
configuration: none
configuration_reason: "Frontend-only change to the team wiki page; no configuration keys or defaults change."
no_action_reason: "Existing wiki data and APIs are unchanged; tree state lives in each browser and starts collapsed."
---
## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

Open a team wiki: the tree is collapsed; expand a page, open another, leave and come back: the same state is restored. In edit mode, rename a page and change its parent, then save.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
