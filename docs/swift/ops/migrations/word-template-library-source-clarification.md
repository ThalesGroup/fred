---
schema: 1
title: "Clarify that Word templates come from configured libraries"
impact: none
configuration: none
configuration_reason: "This change updates capability guidance and descriptions only; template storage and configuration are unchanged."
no_action_reason: "No runtime behavior, data, or deployment configuration changes."
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

The Word capability description identifies configured templates as its source.
A Word file attached in chat remains an ordinary retrieval source and is not
offered as a template base.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
