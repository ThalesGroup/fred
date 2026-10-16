---
schema: 1
title: "Discover corpus spreadsheets and conversation attachments together"
impact: none
configuration: none
configuration_reason: "Uses the existing pod control-plane URL, shared client and document-source settings."
no_action_reason: "Deploy the matching Knowledge Flow and runtime images normally; no stored-data migration or new setting is required."
---
## Applicability

Deployments using tabular tools and conversation CSV or Excel attachments.

## Prerequisites

Retain the existing control-plane URL used for managed agent execution. Publish
and consume the matching fred-runtime and MCP prompt packages with Knowledge
Flow so the additive scope parameters and listing provenance are available.

## Configuration

No new configuration. Existing Attachments and Team documents selections remain
the source ceilings. Conversation discovery uses the existing authenticated
session-attachment route and fails explicitly if that authority is unavailable.

## Upgrade

Deploy compatible runtime and Knowledge Flow images together. Existing corpus
and attachment artifacts are retained; no re-ingestion is required.

## Validation

With both sources enabled, attach a ready CSV or Excel workbook and ask which
spreadsheets are available. One `list_tabular_documents` call should expose the
conversation attachment and authorized corpus documents with their origins.
Describe a listed attachment and query a row beyond the old preview limit.
An attachments-only agent should expose only that conversation's attachments.

## Rollback

Roll both images back together. Previous versions restore separate discovery
for attachments; no stored-data rollback is required.

## Limitations

Old text-backed Excel attachments keep their text path and do not appear as ready
SQL datasets. Unscoped listings do not enumerate attachments across conversations.
