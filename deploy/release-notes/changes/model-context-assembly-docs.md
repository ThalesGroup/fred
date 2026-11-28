---
schema: 1
title: "Document how instructions reach the model"
impact: none
configuration: none
configuration_reason: "Only architecture documentation and code comments change; no configuration keys or defaults change."
no_action_reason: "No runtime behavior, data or API changes; the change is documentation only."
---
## Applicability

Readers of the architecture documentation; no deployed behavior changes.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

Open the architecture chapter "Resources, prompts and skills" and check the section "How instructions reach the model".

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

The section describes the target contract; the following lots of issue #3731 bring the runtime in line with it.
