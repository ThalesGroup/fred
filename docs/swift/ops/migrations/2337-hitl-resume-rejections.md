---
schema: 1
title: "Handle HITL resume conflicts and rejected cancellations"
impact: none
configuration: none
configuration_reason: "Only frontend rejection handling and regression tests change; no configuration keys or defaults change."
no_action_reason: "Existing runtime APIs and stored checkpoints are unchanged; normal frontend deployment applies the fix."
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

Submit an obsolete HITL card and check that the message explains that no answer was applied.
Reject a resume before acceptance and verify that the card remains answerable and
its tools are not falsely displayed as cancelled.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

This change does not recover erased checkpoints or replay an already consumed
approval. The old-checkpoint regression uses SQLite and a fresh graph instance;
it is not a live multi-pod deployment test.
