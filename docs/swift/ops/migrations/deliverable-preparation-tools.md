---
schema: 1
title: "Show preparation tools before long deliverable publication"
impact: none
configuration: none
configuration_reason: "The existing document, presentation and HTML capabilities gain tools without new settings or chart values."
no_action_reason: "Normal deployment exposes the new tools to eligible ReAct agents; existing data and publication contracts need no migration."
---
## Applicability

Fred deployments using the writable document, PPT filler or HTML artifact capabilities.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required. PPT preparation follows the existing configured-template availability.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

Ask a managed ReAct agent to draft a document and confirm `prepare_document_content` appears before `write_document` in the tool trace. Presentation and HTML preparation use `prepare_presentation_content` and `prepare_html_content` when those capabilities are available.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

Preparation uses an extra model round and tool-budget slot. It completes before the model composes the publication arguments, so it does not indicate continuous drafting progress.
