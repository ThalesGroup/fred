---
schema: 1
title: "Make the document retrievability toggle effective on pgvector"
impact: minor
configuration: none
configuration_reason: "Only the pgvector adapter and the toggle's service logic change; no configuration key, default or chart value is added or changed."
---
## Applicability

Deployments whose Knowledge Flow vector store is pgvector. Before this release,
turning a document's retrievability off on pgvector was saved in its metadata
but never reached its indexed chunks, so the document stayed searchable.
OpenSearch, ClickHouse and Chroma deployments need no action.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally. New toggles take effect on the chunks immediately.

Documents switched off **before** the upgrade are still searchable on pgvector
and must have the toggle re-applied once. List them in the Knowledge Flow
database:

```sql
SELECT document_uid, doc -> 'identity' ->> 'document_name' AS name
FROM metadata
WHERE (doc -> 'source' ->> 'retrievable')::boolean IS FALSE;
```

For each one, re-apply the toggle with a user allowed to update the document:
`PUT /knowledge-flow/v1/document/metadata/{document_uid}?retrievable=false`
(idempotent), or switch it on and off again in the document list.

The toggle now fails with HTTP 500 instead of reporting success when the
vector store cannot apply it; the metadata then keeps its previous value and
the request can be retried.

## Validation

Switch a vectorized document off, run a search that matched it, and check it
is no longer returned; switch it back on and check it is returned again. For a
re-applied document, its chunks carry `"retrievable": false`:

```sql
SELECT DISTINCT e.cmetadata ->> 'retrievable'
FROM langchain_pg_embedding e
WHERE e.cmetadata ->> 'document_uid' = '<document_uid>';
```

## Rollback

Use the normal rollback procedure; no data migration is involved. The previous
version already filters search on the chunks' `retrievable` field, so documents
switched off stay hidden, but new toggles stop reaching the chunks again.

## Limitations

pgvector filters retrievability after the nearest-neighbour query (on four
times the requested number of hits, capped at 200). A disabled document never
appears in results, but one whose chunks dominate the nearest neighbours can
reduce the number of hits returned for a query.
