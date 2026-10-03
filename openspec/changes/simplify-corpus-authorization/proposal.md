## Why

Corpus authorization currently enumerates readable documents and sometimes loads
whole folders merely to display their names. With growing teams and corpora, the
cost and correctness depend on corpus size and OpenFGA enumeration limits.
Make the folder the sole authorization boundary, with one authoritative document
membership, instead of optimizing the duplicated document graph.

Tracking: [#2938](https://github.com/ThalesGroup/fred/issues/2938).

## What Changes

- **BREAKING**: each corpus document belongs to exactly one immutable folder;
  no links, multiple memberships, unfiled corpus documents, or document moves.
- OpenFGA owns folder grants and inherited permissions; SQL owns document
  membership. Remove corpus-document tuples and document-wide authorization lists.
- Bound authorization by requested folders or a bounded page, across resource
  browsing, direct reads, retrieval, tabular tools, and agent corpus navigation.
- Separate folder summaries/counts from paginated document contents. Preserve
  session-attachment isolation and existing folder/team permission semantics.
- Align ingestion, synchronization, overwrite, deletion and clean-format
  import/export with this invariant; reject attempted reparenting.
- Validate on fresh installations and consolidate affected documentation.

Existing-deployment translation is a separate offline job with the platform
fully stopped. This change includes neither that job nor an upgrade rollout,
organization/project redesign, graph checkpoints, or unidentified MCP removals.
This branch is separate from the Monday Swift validation baseline.

## Capabilities

### New Capabilities

- `corpus-authorization`: exclusive folder membership, uniform authorization,
  bounded access paths, and fail-closed behavior for the corpus.

### Modified Capabilities

- `document-import-conflicts`: overwriting preserves both document identity and
  its single destination folder; it cannot adopt another folder's document.

## Impact

Cross-component change: fred-core document models and ReBAC schema/client;
Knowledge Flow metadata, tags, ingestion/sync, content and search; runtime corpus
navigation and ReAct/Deep retrieval; control-plane import/export; generated APIs
and Resources UI consumers. Existing databases and clients need a separately
planned version transition. Planning alone changes no executable behavior and
does not close the related correctness/performance issues.
