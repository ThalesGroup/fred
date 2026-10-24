---
schema: 1
title: "Stop reporting chat attachment vectors as corpus orphans"
impact: none
configuration: none
configuration_reason: "Only the corpus audit's classification of vector-only documents changes; no configuration keys, defaults or schemas change."
no_action_reason: "The audit reads existing session-scope chunk metadata through the vector-store adapter at run time; no data, index or schema migration is needed."
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

As a platform administrator, attach a document to a chat conversation, then run
the corpus audit. The attachment's document UID no longer appears with
`orphan_vectors`; vectors without a metadata row that are not chat attachments
are still reported.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.
Rolling back makes chat attachments appear as `orphan_vectors` again.

## Limitations

When the vector store cannot classify a document, the audit keeps reporting it
as `orphan_vectors` and logs a warning, so a real orphan is never hidden.
