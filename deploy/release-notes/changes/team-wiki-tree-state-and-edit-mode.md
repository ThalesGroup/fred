---
schema: 1
title: "Team wiki remembers its tree and edits title, parent and deletion in edit mode"
impact: none
configuration: none
configuration_reason: "Only frontend components and translations change; no configuration key or default changes."
no_action_reason: "The Control Plane wiki contract and schema are unchanged, and tree state lives in each browser."
---
## Applicability

New Weaver installations. Weaver supports fresh installations only, so there is no upgrade path to consider.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

Open a wiki: the tree starts collapsed. Expand a page, open another, leave and come back: the same state returns. In edit mode, rename a page and change its parent, then save.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

Tree state is kept per browser. Title and parent are saved before the text, so a conflict on the text leaves the rename applied.
