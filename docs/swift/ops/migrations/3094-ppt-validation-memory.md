---
schema: 1
title: "Reduce PowerPoint validation memory and clarify transport failures"
impact: none
configuration: none
configuration_reason: "Validation reuses one parsed deck and collects worker cycles; the existing four-job limit, API routes, and deployment values are unchanged."
no_action_reason: "The validation fix and translated transport messages apply during normal deployment; stored templates, agent configuration, and permissions remain compatible."
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

Select and save a valid PowerPoint template repeatedly and confirm validation succeeds. Check that unreachable-runtime, timeout, and interrupted-validation errors show distinct localized messages without internal URLs.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

The four-job admission bound is unchanged and is not a memory budget. Very large concurrent decks can still exceed the pod limit; the local repeated-cycle measurement does not establish production concurrency capacity.
