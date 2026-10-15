---
schema: 1
title: "Show the case-sensitive switch in platform access rules"
impact: none
configuration: none
configuration_reason: "Only the rule editor's page-local CSS changes; no configuration keys or defaults change."
no_action_reason: "The access rule API and saved policies are unchanged; the switch appears after a normal frontend deployment."
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

As a platform administrator, open Administration > Platform access > Rules. In a
condition row, verify that the switch under "Case sensitive" is visible and can
be changed. On a narrow screen, verify that its text label and switch appear
together.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No operational limitations apply; the existing comparison behavior and saved
policy format are unchanged.
