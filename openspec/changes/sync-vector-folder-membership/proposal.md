## Why

Linking an indexed document into a second folder updates its stored membership
but not the folder ids copied onto its vector chunks. Corpus search pre-filters
chunks on those copies, so the document never appears when searching the new
folder. Confirmed on pgvector and OpenSearch; ClickHouse, Chroma and the
in-memory store copy tags the same way. Library sync refiling uses the same
path. Tracking: [#3199](https://github.com/ThalesGroup/fred/issues/3199).

## What Changes

- Every vector store implements one required operation that replaces the
  folder ids on all chunks of a document.
- Linking, unlinking and refiling a vectorized document write the new folder
  ids to the vector store before saving its metadata. A vector failure aborts
  the change and is reported; nothing reports success while chunks are stale.
- Chroma's folder filter matches a folder inside a multi-folder list instead
  of only single-folder chunks, so a linked document stays searchable there
  (also the fix proposed in [#3001](https://github.com/ThalesGroup/fred/issues/3001)).
- The search path is unchanged: no per-query membership lookup is added.

Not in scope: an automatic backfill of documents linked before this change,
the ingestion race where a link lands while a document is being vectorized,
and the one-folder-per-document direction in `simplify-corpus-authorization`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `team-resource-spaces`: folder membership changes reach the search index.

## Impact

Knowledge Flow vector store adapters (OpenSearch, pgvector, ClickHouse, Chroma,
in-memory), `MetadataService` link/unlink, and their offline tests. No API,
schema, configuration or frontend change. Migration note (impact `minor`):
documents linked to an extra folder before this release stay unsearchable there
until re-linked or re-processed.
