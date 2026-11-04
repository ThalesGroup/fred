---
schema: 1
title: "Use the verified exporter's name in Word document properties"
impact: none
configuration: none
configuration_reason: "DOCX export uses the existing verified identity; no identity, directory or capability configuration changes are needed."
no_action_reason: "Normal deployment updates export metadata only, without stored-data migration or additional operator action."
---
## Applicability

Fred deployments using the writable_document capability to export Word documents.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required. No directory lookup is added.

## Upgrade

Deploy Fred normally. Newly exported DOCX files set Author and Last modified by
to the exporter's trimmed verified first and last names when both are present,
otherwise to their trimmed verified username. Both properties are explicitly
empty when no reliable name is available. Each is limited to 255 characters.
Previously downloaded files and stored Fred documents are not changed.

## Validation

After deployment, export a document from the chat card and editor panel. Inspect
Author and Last modified by in Word or LibreOffice against the authenticated
profile, and verify that Markdown export remains unchanged. This is an operator
check to perform, not a claim of completed end-to-end validation.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.
Rollback restores the previous export metadata behavior for future downloads.

## Limitations

Delegated AssertedUser identities have no profile and export with both author
properties empty. User IDs and workload names are deliberately never substituted.
The Word author identifies the exporter, not necessarily the content's writer.
Content, document ownership and access controls remain unchanged.
