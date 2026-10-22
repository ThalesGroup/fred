---
schema: 1
title: "Distinguish skill badges with animated spectrum text"
impact: none
configuration: none
configuration_reason: "Only skill badge presentation, visible labels and selection-copy serialization change; configuration keys and defaults are unchanged."
no_action_reason: "Stored invocations and APIs are unchanged; the badge appearance takes effect with normal frontend deployment."
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

Send a selected skill in chat. Confirm the shared spectrum moves from left to right through the skill name and icon without a filled background, outline or leading slash. Open its preview by mouse and keyboard and confirm it still copies as a canonical /name invocation. With reduced motion enabled, confirm the spectrum remains still.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
