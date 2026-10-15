## Why

[#2845](https://github.com/ThalesGroup/fred/issues/2845) demonstrates that truncated OpenFGA document inventories make populated folders appear empty and let folder deletion leave documents behind. PostgreSQL already stores the actual folder membership; this change fixes these operations without changing the current permission model.

## What Changes

- Authorize known document candidates with bounded individual READ checks instead of intersecting them with global document ListObjects results. Cover explicit UID reads, single/multiple-folder inventories and paginated folder browsing.
- Deduplicate checks within each candidate batch and preserve multi-folder documents, delegated callers and disabled-ReBAC behavior.
- Use canonical SQL subtree/document membership for document-folder deletion, with existing permissions checked explicitly. Do not interpret filtered-out or unresolved items as an empty folder.
- Refuse folder removal if its known contents cannot be processed or canonical membership remains. Keep the existing sequential subtree traversal and bounded document-removal batches.
- Add regression coverage above 1,000 readable documents, permission denials/failures, multi-folder preservation and checks whose cost follows the requested candidates.

This is the bounded folder-inventory slice of #2845, not the abandoned team-only corpus redesign. It does not complete every item in the original issue: historical orphan repair, global discovery/label inventories and general ListObjects completeness remain explicitly tracked. Artifact cleanup recovery stays in #2144; partial multi-library revocation stays in #3121. Do not automatically close #2845 while these remaining items are unresolved.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `team-resource-spaces`: complete authorization of known folder documents and safe use of canonical membership during folder removal.

## Impact

Knowledge Flow metadata/tag services, their existing SQL stores where subtree selection requires it, focused offline tests and the existing validation campaign. Update the existing deployment guidance and add one migration note describing no schema/configuration migration. No FGA schema, frontend contract, storage layout or Rust POC changes.
