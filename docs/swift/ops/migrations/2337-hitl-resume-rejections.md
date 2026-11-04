---
schema: 1
title: "Handle HITL resume conflicts and rejected cancellations"
impact: none
configuration: none
configuration_reason: "Runtime history availability, frontend notifications, regression tests, and CI scanner installation change; no deployment configuration keys or defaults change."
no_action_reason: "The optional history availability field is additive; stored checkpoints and database schema are unchanged. Deploy runtime and frontend normally."
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
its tools are not falsely displayed as cancelled. Reload a consumed question and
verify it is readable without response controls; a genuinely pending question
remains answerable. Navigate to an admin page while a turn continues and verify
its human-input toast opens the originating conversation.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

This change does not recover erased checkpoints or replay an already consumed
approval, reconnect streaming, or persist disconnected-turn history. Older
runtimes without the availability annotation retain legacy card reconstruction.
The old-checkpoint regression uses SQLite and a fresh graph instance;
it is not a live multi-pod deployment test.
