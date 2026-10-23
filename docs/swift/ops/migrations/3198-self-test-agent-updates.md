---
schema: 1
title: "Allow editing and toggling the self-test harness agent"
impact: none
configuration: none
configuration_reason: "Only the control-plane agent-update admission check changes; no configuration keys, defaults or schemas change."
no_action_reason: "The self-test harness templates were already exempt from the template capability gate at enrollment; the update path now applies the same existing exemption, with no data, tuple or schema migration."
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

As a platform admin, enroll the self-test agent in your personal space, then
disable it and update its system prompt. Both
`PATCH /control-plane/v1/teams/{team_id}/agent-instances/{agent_instance_id}`
calls return HTTP 200 instead of HTTP 403. An instance of an ordinary template
whose access was revoked is still refused with HTTP 403.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
