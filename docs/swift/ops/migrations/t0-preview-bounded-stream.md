---
schema: 1
title: "Stream platform access T0 previews in bounded batches"
impact: none
configuration: none
configuration_reason: "The T0 preview changes only its internal user scan; no configuration keys or defaults change."
no_action_reason: "The preview response and one-time import behavior stay unchanged, so normal deployment is sufficient."
---

## Applicability

Existing Fred deployments that use the Platform access administration page.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no data migration or operator action is required.

## Validation

Open Platform access, then Users. The T0 preview should show the existing candidate and matching totals.

## Rollback

Use the normal rollback procedure; this change does not alter stored data.

## Limitations

The preview still evaluates every known user. It keeps one database cursor open during the scan, so total calculation time grows with the user population.
