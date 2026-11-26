---
schema: 1
title: "Keep Deep child deliverables with the parent"
impact: none
configuration: none
configuration_reason: "The capability manifest adds a defaulted runtime declaration; saved agent settings and chart values are unchanged."
no_action_reason: "Existing data and APIs are unchanged; the child tool filtering and evidence aggregation take effect on normal deployment."
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

Ask a Deep agent to delegate research and prepare a file. Child sources should appear in the final answer, while the parent creates any downloadable file card.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

Third-party capabilities that publish deliverables must set `available_to_subagents=False` in their manifests to keep those tools on the Deep parent.
