---
schema: 1
title: "Extend shared UI components for hosted applications"
impact: none
configuration: none
configuration_reason: "Only shared frontend components and the independent UI npm candidate change; no deployment configuration or defaults change."
no_action_reason: "FRED keeps its existing translated screens and interactions; no data, permissions, APIs or deployment ordering change."
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

Open evaluation runs and confirm status badges, KPI state labels and table pagination retain their current behavior. The independent npm candidate must additionally pass archive, isolated-consumer and both-theme browser checks.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

Publishing alpha.3 and adopting it in the standalone evaluation application are separate follow-up operations, not required for upgrading FRED.
