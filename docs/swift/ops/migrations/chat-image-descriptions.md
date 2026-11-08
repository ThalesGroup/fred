---
schema: 1
title: "Exhaustive descriptions for images and SVG attached to the chat"
impact: none
configuration: none
configuration_reason: "Knowledge Flow reuses the existing vision_model setting and the LibreOffice and PDFium renderers its image already ships; no configuration key or default changes."
no_action_reason: "Only the description prompt, SVG summarizing, the attachment context and the agent prompt change; new uploads get the new description with a normal deployment, and existing attachments keep working."
---
## Applicability

Existing Fred deployments upgrading to this release; only chat image and SVG attachments.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required. Image
summaries grow to about 6,000 characters. Each SVG upload renders once with
LibreOffice (about 220 MB, at most two at a time per Knowledge Flow process).

## Validation

Attach a chart and ask about one of its values: the agent answers from the
description and says so.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

Attachments uploaded before the upgrade keep their previous summary.
