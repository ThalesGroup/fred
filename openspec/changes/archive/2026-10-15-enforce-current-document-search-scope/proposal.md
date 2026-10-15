## Why

The live OpenSearch validation for [#3091](https://github.com/ThalesGroup/fred/issues/3091) reproduces corpus disclosure outside the active team through explicit document IDs and after removal from a library through stale vector tags. It also shows that selecting a corpus document suppresses conversation attachments.

## What Changes

- Constrain explicit corpus document IDs to the current authorized ownership context as well as document READ permission.
- Validate corpus search candidates against current metadata and permissions before exposing content; stale vector tags cannot grant access or satisfy an obsolete library selection.
- Preserve library-plus-document union semantics, document-only narrowing, and independent user/session attachment scope.
- Use the existing regression campaign as acceptance, with additional focused tests for missing metadata, authorization failures and bounded per-request work.

This is the search containment slice of #3091. Retry repair of partially failed metadata/OpenFGA unlink operations (scenario 4b), other document tools and the unproven UI upload race remain separate work; this slice does not close the entire issue.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `team-resource-spaces`: current corpus membership and contextual authorization govern search results; corpus selection does not suppress enabled conversation attachments.

## Impact

Knowledge Flow vector search orchestration and metadata authorization helpers, their offline tests, the existing validation campaign and the PR's migration note. No public request schema, database migration or new dependency is intended.

The existing `simplify-corpus-authorization` change replaces the ownership model with projects and immutable folders; it explicitly separates this validation branch. Extending that proposal would couple an immediate fix to an unimplemented migration. `split-attachments-and-team-documents` changes capability settings, not Knowledge Flow retrieval. This bounded fix instead extends the shipped `team-resource-spaces` specification and preserves today's multi-library model.
