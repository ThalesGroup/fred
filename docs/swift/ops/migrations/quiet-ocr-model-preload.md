---
schema: 1
title: "Preload OCR models without ONNX Runtime build warnings"
impact: none
configuration: none
configuration_reason: "Only the build-time model preload method changes; runtime configuration and model selection stay the same."
no_action_reason: "The image contains the same OCR model packages and recognition dictionary, so normal deployment is sufficient."
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

Check that the knowledge-flow image builds and OCR processes a document successfully.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
