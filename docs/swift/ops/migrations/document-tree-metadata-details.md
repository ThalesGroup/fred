---
schema: 1
title: "Expose document metadata and filesystem tool details"
impact: none
configuration: none
configuration_reason: "No deployment configuration keys or permissions change. The existing tree character budget increases to 20,000 by default and 60,000 maximum."
no_action_reason: "Normal deployment updates the renderer, capability and frontend. Existing metadata is reused, historical results remain readable, and no database or API schema migration is needed."
---
## Applicability

Deployments using the document access capability and its document tree tool.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally. The tool's existing tree string now contains compact JSON document leaves with timestamps and descriptive metadata; its request and response shapes are unchanged. Deploy the aligned 20,000-character default and 60,000-character maximum with the corresponding frontend. This update also fixes the first message handoff while the chat session is being created.

## Validation

Ask an agent to list a document folder and open the tool detail. Check the nested file tree and hover or keyboard-focus a file to see its metadata. Dates stay out of file rows; file creation, modification and format stay out of the tooltip. Internal ids remain hidden. A pruned result has a small Truncated footer. From a fresh chat, submit its first message once and verify that the turn starts without a second submit; leaving during session creation must not start a late turn.

## Rollback

Use the normal rollback procedure. No stored document data is changed.

## Limitations

Arrival is the stored date of addition to Fred, not an ingestion-completion event. Missing legacy arrival dates remain unknown. A partial tree cannot identify the latest document across its entire requested scope. Historical text results retain their original upload-date meaning. Deploy the corresponding backend, capability and frontend versions together for the new detail view.
