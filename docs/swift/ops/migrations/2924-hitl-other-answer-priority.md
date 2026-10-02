---
schema: 1
title: "Prioritize Other text in HITL answers"
impact: none
configuration: none
configuration_reason: "Only managed chat answer selection changes; no configuration keys or defaults change."
no_action_reason: "Normal frontend deployment is sufficient; existing HITL requests, responses, and APIs remain compatible."
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

In managed chat, select a choice in an agent question, then enter a different answer in Other. Submit the question and confirm that only the Other text appears in the response. With several questions, use Next on the last tab and confirm it opens the first unanswered tab, skipping tabs already answered.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
