---
schema: 1
title: "Keep vector chunk folders in sync when documents are linked, unlinked or refiled"
impact: minor
configuration: none
configuration_reason: "Only Knowledge Flow code changes; no configuration key, default, chart value or schema changes."
---
## Applicability

Deployments where users link an already indexed document to another folder,
remove it from one of several folders, or where library sync moves documents
between folders. Every vector store is concerned: OpenSearch, pgvector,
ClickHouse, Chroma and the in-memory development store.

Before this release a link changed only the document's stored membership. Its
indexed chunks kept the folder ids from ingestion, so corpus search never found
the document from a newly linked folder. From this release, link, unlink and
refile update the chunks first and fail the request if the vector store rejects
the update. No search request is slower.

## Prerequisites

The vector store must be reachable when users link or unlink documents: a link
now fails instead of silently leaving the index stale.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Knowledge Flow normally. This is enough for every link, unlink and
refile made after the upgrade.

Optional remediation: documents whose folders changed after ingestion and
before this upgrade keep stale chunk folders, and stay unsearchable from the
folders they were added to. No automatic backfill is shipped. To list the most
likely candidates (vectorized documents in more than one folder), run on the
Knowledge Flow PostgreSQL database:

```sql
SELECT document_uid, tag_ids
FROM metadata
WHERE cardinality(tag_ids) > 1
  AND doc #>> '{processing,stages,vector}' = 'done';
```

To repair one document, link it to any additional folder and then remove it
from that folder again. Each step rewrites the folders on all of its chunks
from its current membership; nothing is re-embedded. Never remove a
document's only folder: that deletes the document. A document that was moved
(linked elsewhere, then removed from its original folder) has one folder and
is not listed by the query; repair it the same way if search in its folder
misses it.

## Validation

Link an indexed document from folder A to folder B, then search only folder B
in a conversation: the document is returned. Remove it from A: a search of A no
longer returns it and B still does. With the vector store stopped, a link
attempt fails and the document stays only in A.

## Rollback

Use the normal rollback procedure. Chunk folders written by this release remain
valid for the previous one; links made after a rollback are stale again.

## Limitations

ClickHouse updates the `tag_ids` column search filters on; the JSON metadata
copy shown by the raw chunk view keeps ingestion-time folders. A link made
while the document is still being vectorized can be overwritten by the chunks
that ingestion writes afterwards. Chroma now stores a non-empty folder list
as a native array, which requires the pinned chromadb 1.5.x. Verified offline
and with a live pgvector chunk update; live OpenSearch and a full live search
were not exercised.
