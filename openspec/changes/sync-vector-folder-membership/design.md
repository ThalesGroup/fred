## Context

A document's folder membership lives in its metadata row (`tags.tag_ids`) and
in ReBAC parent relations. At vectorization the same ids are copied onto every
chunk. Search narrows candidates in the vector store with those copies
(`SearchFilter.tag_ids`), then re-checks each candidate against stored
membership and ReBAC (`team-resource-spaces`: stale index membership cannot
authorize a hit). Link and unlink (`MetadataService.add_tag_id_to_document`,
`remove_tag_id_from_document`, also used by library sync refiling) only
changed the row, so a newly linked folder never reached the pre-filter.

## Goals / Non-Goals

**Goals:** a vectorized document is searchable from exactly the folders it
currently belongs to, on every vector store; a failed index update is reported,
never hidden behind a successful response; the search hot path is unchanged.

**Non-Goals:** backfilling documents linked before this change; the race where
a link lands while the document is being vectorized; moving to one folder per
document (`simplify-corpus-authorization`).

## Decisions

### Propagate membership to chunks, not membership to search

Each adapter implements `set_document_tag_ids(document_uid, tag_ids)`, a
required (abstract) method next to the existing `set_document_name` and
`set_document_retrievable` per-document metadata updates. It replaces the ids
in one store operation: an OpenSearch `update_by_query`, one pgvector `UPDATE`
with `jsonb_set`, one ClickHouse mutation on the promoted `tag_ids` column, one
Chroma `update` of the document's chunks, and an in-place update in memory.
Required rather than optional because a store that cannot apply it cannot honor
folder filters at all.

Rejected: resolving the selected folders to document uids from PostgreSQL at
search time. It removes the copy but adds a membership query to every search,
turns a folder filter into a potentially large uid filter on each backend, and
needs its own performance review. Link and unlink are rare; search is the hot path.

### Write the index first, then the metadata row

Link and unlink compute the new id list, write it to the vector store, and only
then save the row, storage accounting and ReBAC relation. A vector failure
therefore leaves the change undone and raises `MetadataUpdateError`. If the
later save fails, the error still surfaces and the retry takes the normal path
again (the row is unchanged), re-applying both writes idempotently. Writing the
row first would leave a committed link with a stale index; the retry would then
land on the "already present" branch and never repair the chunks.

The residual window is benign: after a failed save, a linked chunk carries an
extra folder that search drops against stored membership, and an unlinked
chunk already lacks the folder the user is removing.

The update runs in `asyncio.to_thread`, like rename, because every adapter
client is synchronous. It is skipped for documents that never reached the
`VECTORIZED` stage. Removing the last folder keeps its existing behavior
(delete the vectors).

### Chroma matches one folder inside a multi-folder list

Chroma stored every list as a JSON string, and its folder filter compared the
whole string with `["<id>"]`, so a chunk with two folders matched neither
([#3001](https://github.com/ThalesGroup/fred/issues/3001)). Without that fix,
linking would hide a document from both folders on Chroma. A non-empty
`tag_ids` is now stored as a native array (Chroma rejects empty arrays, which
keep the JSON form) and the filter is an `$or` of `$contains` per id, plus the
old one-folder `$in` so chunks indexed before stay matched. Applied as its own
commit so it can ship with #3001 separately.

### ClickHouse updates the promoted column only

ClickHouse search filters on the `tag_ids` column. Its JSON `metadata` copy
keeps the ingestion-time ids; rewriting it would cost one mutation per chunk
(as rename does). Search responses already replace hit `tag_ids` with stored
membership, so only the raw chunk inspector shows the older copy.

## Risks / Trade-offs

- [A link now fails when the vector store is down] → Intended: success would
  otherwise leave the document unsearchable from the new folder.
- [Documents linked before this change keep stale chunk ids] → Migration note
  gives the operator remediation (re-link or re-process); no automatic backfill.
- [Concurrent link and unlink on one document can overwrite each other's id
  list] → Same last-writer-wins race the metadata row already has; unchanged.

## Migration Plan

Deploy normally. Optional remediation for previously linked documents is in the
migration note. Rollback restores the stale-copy behavior; ids written by this
version stay valid for the previous one.
