## Why

[#2845](https://github.com/ThalesGroup/fred/issues/2845): above 1,000 readable documents, OpenFGA `ListObjects` silently truncates. The folder inventory slice is fixed; tabular agent tools, labels, document listing and resource listing still authorize by enumerating every readable document. In production an agent's workbook was missing from `list_tabular_documents` and returned 404 on `describe` and `read_query` while `Check` allowed it.

The model already makes the enumeration unnecessary: `document#read` and `resource#read` are both `read from parent`. A document is readable exactly when one of its tags is.

## What Changes

- Knowledge Flow stops enumerating documents and resources in OpenFGA. Readable documents are those whose stored tags intersect the caller's authorized tags: the active scope's tags when one is set, otherwise the caller's readable tags.
- Tabular resolution, `get_documents_metadata`, label lookups and resource listing use that rule. The evaluation-worker special case in tabular resolution folds into the scoped path.
- Label store queries narrow by tag ids in SQL instead of an expanded document-uid list.
- The remaining enumerations (folders, teams, file areas) keep the plain `ListObjects` call. `lookup_resources` logs a warning when a response reaches the server's default 1,000-result limit or nears its default deadline, so a truncation can no longer go unnoticed.

Not in scope: historical orphan repair (issue item 4), the per-candidate checks added for folder inventories, the FGA model, and the organization/project redesign (`simplify-corpus-authorization`). Do not close #2845 automatically.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `team-resource-spaces`: document and resource visibility derive from authorized folders, independent of corpus size; possibly truncated authorization enumerations are logged.

## Impact

`fred-core` (OpenFGA engine, document label store), Knowledge Flow metadata, tabular and resource services, their offline tests and the folder-inventory validation scenario. One migration note (impact: none) recommending operators review `listObjectsDeadline`. No schema, API, frontend or FGA model change.
