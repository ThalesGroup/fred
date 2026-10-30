---
schema: 1
title: "Disclose partial native skill reads"
impact: none
configuration: none
configuration_reason: "Only skill guidance, additive activity metadata and frontend labels change; no configuration keys or defaults change."
no_action_reason: "Normal deployment suffices. Existing history remains readable, and native pagination and pinning keep their current behavior."
---
## Applicability

Fred runtimes and frontend displaying native Deep skill-load activity.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required. Native read limits are unchanged.

## Upgrade

Deploy normally. New skill-read activity can carry an additive `partial` flag;
older history without it retains its existing presentation.

## Validation

Read only the first page of a longer skill. Confirm the activity says
"Skill partially loaded" or "Skill partiellement chargé", including after
reloading history. Complete loads keep the existing label.

## Rollback

Use the normal rollback procedure; this introduces no data migration.

## Limitations

The label describes the individual read, not cumulative page coverage. Prompt
guidance requests 1000 lines and continuation but does not enforce model behavior.
