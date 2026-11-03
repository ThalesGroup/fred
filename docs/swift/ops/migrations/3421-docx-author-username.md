---
schema: 1
title: "Use the authenticated username in exported Word document metadata"
impact: none
configuration: none
configuration_reason: "Only writable-document DOCX metadata changes; no configuration keys or defaults change."
no_action_reason: "New Word downloads use the existing authenticated username without changing stored documents, APIs, or permissions. Normal deployment is sufficient."
---
## Applicability

Existing Fred deployments using writable-document Word exports.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

Export a writable document as Word and check that its author and last-modified-by
properties contain the authenticated user's username instead of python-docx.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

Previously downloaded files retain their metadata. Export the document again to
obtain the corrected metadata. Usernames longer than Word's 255-character
property limit are truncated in the exported metadata.
