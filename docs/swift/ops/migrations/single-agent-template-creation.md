---
schema: 1
title: "Open agent creation directly when one template is available"
impact: none
configuration: none
configuration_reason: "Only the frontend creation flow changes; no deployment configuration or permissions change."
no_action_reason: "Existing agent data and APIs are unchanged; the new flow takes effect with a normal frontend deployment."
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

In a team or personal space with one available agent template, click Create agent and confirm that the configuration form opens directly with the template name in the subtitle. With multiple templates, confirm that the template browser still opens.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
