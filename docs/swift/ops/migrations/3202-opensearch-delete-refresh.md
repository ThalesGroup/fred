---
schema: 1
title: "Make deleted document vectors immediately invisible in OpenSearch"
impact: none
configuration: none
configuration_reason: "Only the OpenSearch delete_by_query request options in Knowledge Flow change; no configuration keys, defaults or schemas change."
no_action_reason: "The index, mappings and stored vectors are unchanged; the deletion refresh takes effect with normal deployment."
---
## Applicability

Existing Fred deployments upgrading to this release that use OpenSearch as the
Knowledge Flow vector store. Pgvector deployments are unaffected.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required. Each
document vector deletion now triggers one OpenSearch index refresh; bulk purges
of many documents perform one refresh per document.

## Validation

Delete a vectorized document, then immediately run the corpus audit or a search
that previously matched it: none of its chunks are reported or returned, without
waiting for the periodic index refresh.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.
After rollback, deleted chunks can again stay visible for up to one refresh
interval.

## Limitations

Single-chunk deletion from the chunk administration view is unchanged and still
becomes visible on the next periodic refresh.
