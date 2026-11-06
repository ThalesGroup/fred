---
schema: 1
title: "Keep a streamed chat answer running when the user navigates elsewhere in Fred"
impact: none
configuration: none
configuration_reason: "Only frontend stream ownership changes; no configuration keys, defaults or chart values are involved."
no_action_reason: "The runtime and its APIs are unchanged; the browser simply keeps the existing stream open, so normal deployment is enough."
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

Ask an agent a question with a long answer, open another conversation while it
streams, then come back: the answer is still streaming, or complete if it ended
meanwhile.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

Reloading or closing the tab during an answer still loses that turn.
