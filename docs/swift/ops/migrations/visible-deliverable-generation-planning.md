---
schema: 1
title: "Plan visible deliverable generation before publication"
impact: none
configuration: none
configuration_reason: "This draft adds OpenSpec planning documents only; application configuration and chart values are unchanged."
no_action_reason: "No runtime behavior, API, stored data, or deployment artifact changes in this planning-only draft."
---

## Applicability

This planning-only draft describes a proposed preparation/composition/publication
workflow. It does not yet ship the tools or frontend labels.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

Validate the planning artifacts with
`openspec validate show-deliverable-generation-progress --strict`.
The proposed generation indicators are not available until implementation.

## Rollback

Use the normal rollback procedure; this draft introduces no data migration.

## Limitations

Reconcile this declaration with the actual implementation before making the PR
ready for final review. Operator impact has only been assessed for this draft's
planning documents.
