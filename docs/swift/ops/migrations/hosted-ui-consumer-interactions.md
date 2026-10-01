---
schema: 1
title: "Complete hosted UI consumer interactions"
impact: none
configuration: none
configuration_reason: "Optional shared component props do not change deployment configuration."
no_action_reason: "Existing consumers retain their current default interactions and styling."
---

## Applicability

Fred deployments and consumers of the unpublished UI alpha.3 candidate.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally. Hosted consumers can opt into typed table-row activation,
a localized drawer close label and semantic KPI tones after the UI package release.

## Validation

In the evaluation application, activate a run row with Enter, close the case drawer
using its localized close action, and inspect outcome KPI values in both themes.

## Rollback

Use the normal rollback procedure. No data migration is involved.

## Limitations

The candidate archive must be rebuilt and release evidence regenerated before
publication. Evaluator registry pins remain pending the package release.
