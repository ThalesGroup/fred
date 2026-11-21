---
schema: 1
title: "Keep Deep child deliverables with the parent"
impact: none
configuration: none
configuration_reason: "The capability manifest adds a defaulted runtime declaration; saved agent settings are unchanged."
no_action_reason: "No data or API migration is needed; child tool filtering and evidence aggregation take effect on normal deployment."
---

## Applicability

New Weaver deployments using Deep agents.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

Ask a Deep agent to delegate research and prepare a file. Child sources should appear in the final answer, while the parent creates any downloadable file card.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

Third-party capabilities that publish deliverables must set `deep_child_enabled=False` in their manifests to keep those tools on the Deep parent.
