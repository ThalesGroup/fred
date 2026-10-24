---
schema: 1
title: "Verify frontend package dependencies against retained candidate evidence"
impact: none
configuration: none
configuration_reason: "The change only corrects release-time registry evidence; application and deployment configuration are unchanged."
no_action_reason: "Existing Fred deployments do not change; release maintainers can resume the retained frontend publication through the normal workflow."
covers:
  - 0bccca318648c751a1ddb4c648ff901d61191a42
---

## Applicability

Frontend package release maintainers resuming a retained publication after a registry verification failure.

## Prerequisites

Use the original candidate artifact and every retained publishing attempt and terminal reference.

## Configuration

No application or deployment configuration changes are required.

## Upgrade

Deploy Fred normally. For the interrupted frontend release, dispatch the existing
publish operation after this fix reaches swift, using the original release evidence.

## Validation

Confirm that registry reconciliation verifies UI and its design-tokens dependency
against the same retained candidate before it publishes the untouched iframe SDK.
Verify the exact SDK version, archive integrity, and provenance in the public registry.

## Rollback

Use the normal code rollback procedure; public npm versions cannot be unpublished
or republished as part of this rollback.

## Limitations

The existing release workflow still requires complete retained artifacts and
cryptographic provenance. Registry visibility delays can still require a later
read-only verification run.
