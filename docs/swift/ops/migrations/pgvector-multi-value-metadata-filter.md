---
schema: 1
title: "Search every selected document on pgvector deployments"
impact: none
configuration: none
configuration_reason: "Only the pgvector search filter built inside Knowledge Flow changes; no configuration keys or defaults change."
no_action_reason: "Stored vectors and metadata are unchanged; multi-document filters now reach SQL as an IN clause as soon as Knowledge Flow is redeployed."
---
## Applicability

Existing Fred deployments upgrading to this release. Only deployments whose
Knowledge Flow `vector_store.type` is `pgvector` see a behavior change.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

On a pgvector deployment, select two library documents in the chat document
picker and ask a question that needs both: the answer cites both documents, and
the Knowledge Flow log line `[VECTOR][PGVECTOR][ANN]` shows
`filter={'document_uid': {'$in': [...]}}`.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
