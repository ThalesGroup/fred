---
schema: 1
title: "Control plane endpoints to copy an agent to other teams or the personal space"
impact: none
configuration: none
configuration_reason: "New API routes only; no configuration key, default or chart value changes."
no_action_reason: "Agent-copy endpoints are additive, use the existing agent table and call the matching pods' copy-config operation; the frontend copy action ships in this release."
---

## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

The agent pods should run a release that serves
`POST /agents/capabilities/{id}/copy-config`. With older pods, a copied agent is
created without its capabilities, and each one is reported as left out.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator action is required.

## Validation

`GET /control-plane/v1/teams/{team_id}/agent-instances/{id}/copy-targets` on an
agent you edit lists your personal space and your teams.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.
Agents already copied stay valid.

## Limitations

No additional migration limitations identified for this change.
