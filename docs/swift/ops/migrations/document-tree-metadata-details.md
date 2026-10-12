---
schema: 1
title: "Expose document metadata and compact tool details"
impact: none
configuration: none
configuration_reason: "Only the existing document tree tool payload and its chat detail view change; no configuration keys, permissions or defaults change."
no_action_reason: "Normal deployment updates the renderer, capability and frontend. Existing metadata is reused, historical results remain readable, and no database or API schema migration is needed."
---
## Applicability

Deployments using the document access capability and its document tree tool.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally. The tool's existing tree string now contains compact JSON document leaves with timestamps and descriptive metadata; its request and response schemas are unchanged.

## Validation

Ask an agent to list a document folder and open the tool detail. Check that document name, format and arrival date are visible, that expanding a document shows available metadata, and that internal ids are hidden. For a pruned result, verify that the partial-listing warning remains visible.

## Rollback

Use the normal rollback procedure. No stored document data is changed.

## Limitations

Arrival is the stored date of addition to Fred, not an ingestion-completion event. Missing legacy arrival dates remain unknown. A partial tree cannot identify the latest document across its entire requested scope. Historical text results retain their original upload-date meaning. Deploy the corresponding backend, capability and frontend versions together for the new detail view.
