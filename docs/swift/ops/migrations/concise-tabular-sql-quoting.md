---
schema: 1
title: "Shorten tabular SQL quoting instructions"
impact: none
configuration: none
configuration_reason: "Only packaged tabular prompt wording changes; no configuration keys, defaults or chart values change."
no_action_reason: "The shorter instructions load with the normal agent pod deployment; existing data, APIs and query execution need no migration."
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

Check that the packaged tabular instructions show `O'Reilly` encoded as `'O''Reilly'`, scope the backslash warning to ordinary SQL strings, and distinguish SQL quoting from JSON encoding.

## Rollback

Use the normal rollback procedure to restore the previous wording; no data migration is involved.

## Limitations

This editorial change preserves quoting guidance but does not guarantee model compliance or add automatic SQL correction.
