---
schema: 1
title: "Generated migration guides use keyboard characters only"
impact: none
configuration: none
configuration_reason: "Only the release tooling that renders migration guides changes; no setting is involved."
no_action_reason: "Deployed applications are unchanged; only the punctuation of generated release guides differs."
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

The release's generated `migration.md` contains only ASCII characters in its title and impact lines.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
