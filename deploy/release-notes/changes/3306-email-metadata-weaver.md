---
schema: 1
title: "Preserve structured metadata from ingested email"
impact: none
configuration: none
configuration_reason: "The existing email worker contract and metadata artifact carry the new fields."
no_action_reason: "The change applies to newly processed email files during normal deployment."
---
## Applicability

Weaver deployments that ingest `.eml` or `.msg` files into a library.

## Prerequisites

The email extraction worker contract introduced by the Swift-to-Weaver merge must be active.

## Configuration

No configuration changes are required.

## Upgrade

Deploy the updated worker normally. Newly processed email documents include the subject, sender and sent date in document metadata and vector indexing. Selected routing headers are stored under `extensions.email` in the metadata artifact.

## Validation

Ingest an email with a subject, sender and recipients. Check the published metadata artifact for `identity.title`, `identity.author`, `identity.created` and `extensions.email`. Check that Bcc is absent.

## Rollback

Use the normal worker rollback procedure. Previously published metadata artifacts remain intact.

## Limitations

This change does not add email fields to the Control Plane document catalogue or establish `.eml` and `.msg` support for direct chat attachments.
