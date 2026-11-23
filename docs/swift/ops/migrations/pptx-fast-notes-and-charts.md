---
schema: 1
title: "Keep speaker notes and chart data in fast PPTX extraction"
impact: none
configuration: none
configuration_reason: "Only the fast PPTX extractor code changes; no configuration keys or defaults change."
no_action_reason: "The extractor reads the uploaded file only; new attachments benefit after a normal Knowledge Flow deployment."
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

Attach a PowerPoint file with speaker notes and a native chart to a conversation and ask about them: the agent can quote the notes and the chart values.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

Charts are read from their cached values only; pictures of charts are not read.
