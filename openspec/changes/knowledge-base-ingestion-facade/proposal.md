## Why

Knowledge Flow's ingestion API was designed for a person uploading files, and it
serves that well. A Knowledge Base is not a person uploading files: it
synchronizes a source, over and over, and what it needs is the opposite shape.

The mismatch is not cosmetic. Ingestion mints a fresh document identity per
upload, deliberately, so that a person who uploads twice keeps two versions:

```python
def _generate_file_unique_id(self, document_name: str, tags: list[str]) -> str:
    """Previously deterministic (name+tags) which caused later ingests to
    overwrite earlier versions; now use a random UUID to keep each ingestion
    distinct."""
    return uuid.uuid4().hex
```

For a synchronizing pod this is wrong in a way no workaround repairs: every time
a watched file changes, the library gains a copy. A file edited daily leaves a
year of duplicates. The first Knowledge Base written against this API shipped
with exactly that defect, found by running it.

Three further frictions come from the same origin, each measured against a
working pod rather than read off the code:

- **Retraction is a read-modify-write of the whole tag.** A caller must fetch the
  tag, filter its item list, and write it back echoing `name`, `path`,
  `description` and `type` — fields it does not own. Getting one wrong renames
  the user's folder. It also races with any concurrent writer and costs a payload
  proportional to the library.
- **The response is a progress stream, not an outcome.** A caller parses NDJSON
  looking for a failure status; success is the absence of bad news.
- **The writer is recorded as a human.** `KPIActor(type="human", user_id=user.uid)`
  attributes every machine write to a person, so any split of human against
  automated traffic is wrong by exactly the synchronized volume.

## What Changes

A **separate REST surface** for callers that synchronize. The existing ingestion
endpoints are untouched: both models are legitimate, and a person uploading a
file is not doing the same thing as a pod reconciling a source.

**Identity comes from the source, not from the upload.** A caller names each
document by a **source key** it chooses — for most sources, the path relative to
the library. Writing the same key twice updates one document in place, for ever.
The caller never learns, stores or returns a Fred-side identifier.

**Versioning is the source's, and Fred only remembers it.** A caller attaches a
**document version** (an etag, a content hash — whatever its source has) and may
record a **source version** for the library as a whole (a commit sha, a cursor).
Both are opaque: Fred stores them, hands them back, and never interprets them.

This is what makes a pull-mode Knowledge Base able to be driven by its own
source. A pod synchronizing a Git branch asks Fred which version it last
accepted, asks Git what changed since, and sends only that — `git diff` doing the
work no re-implementation would do as well. A source with no version of its own,
such as a local folder, uses per-document versions alone and is served by the
same surface.

**Removal is addressed, not deduced.** A caller removes a document by the same
source key it wrote, without touching the library's tag.

**The writer is recorded as what it is** — a service identity, not a person.

## Capabilities

### New Capabilities

- `knowledge-base-ingestion`: how a system that synchronizes a source writes
  documents into a library it has been granted, addressed by source identity,
  versioned by the source, and reconciled without either side keeping a private
  ledger of Fred-side identifiers.

### Modified Capabilities

None. The existing ingestion surface keeps its behaviour, including its
per-upload versioning, and no caller of it is affected.

## Impact

- **`apps/knowledge-flow-backend`** — the new surface, its authorization, and the
  storage of source keys and versions against documents and libraries.
- **Persistence** — source key and version on a document, source version on a
  library; Alembic migration.
- **`libs/fred-sdk`** — the author-facing synchronization surface that hides this
  protocol entirely (see `knowledge-base-sdk-contract`, which consumes it).
- **Generated API client** — regenerated in the same change, per the repository
  rule.

Explicit non-goals:

- **No change to the existing ingestion endpoints**, and none to their per-upload
  versioning. Migrating the UI onto this surface is a later, separate decision
  that deserves its own verification.
- **No inventory-and-diff exchange in this change.** Letting a caller offer its
  whole inventory and receive back only what Fred wants is the piece that removes
  the last of a caller's own bookkeeping, and it is purely additive on top of
  what is built here. It waits until a real Knowledge Base has shown what its
  bookkeeping actually costs.
- **No interpretation of a source key or version.** They are the caller's
  vocabulary; Fred stores and returns them.
- No re-design of processing, chunking, embedding or retrieval. What a document
  becomes after it is written is unchanged.
