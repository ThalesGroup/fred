---
schema: 1
title: "Prepare the Fred 3.0.1 release documents"
impact: none
configuration: none
configuration_reason: "Only user-facing release notes and the consolidated operator guide are added; no configuration or chart values change."
no_action_reason: "Release documentation introduces no runtime or data change; the prompt-command migration is covered by its own note."
---
## Applicability

Fred 3.0.1 release documentation.

## Prerequisites

Follow the prerequisites in the prompt-command migration procedure.

## Configuration

No configuration changes are introduced by release preparation.

## Upgrade

No additional action for these documents. Follow the prompt-command procedure
in the consolidated guide for the application upgrade.

## Validation

Confirm the application release notes show version 3.0.1 and both GitHub
releases provide the matching migration.md attachment.

## Rollback

Documentation adds no rollback operation; follow the prompt-command rollback
procedure for its schema change.

## Limitations

These documents do not publish images or charts; both release workflows must
complete successfully.
