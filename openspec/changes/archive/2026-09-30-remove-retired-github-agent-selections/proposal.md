## Why

Existing managed agents can still select `mcp-web-github-readonly` after its
unimplemented MCP entry was removed. Execution then fails with
`UnknownCapabilityError`. The previous data revision only cleans the retired RAG
MCP ID; this corrects the missed GitHub selection tracked by issue #2708.

## What Changes

- Extend the existing retired-MCP data revision to remove the plain and historic
  `mcp:`-prefixed GitHub ID from persisted capability selections and config.
- Preserve other tuning, inheritance semantics, agent metadata and permissions;
  do not select a replacement capability.
- Document the operator upgrade and verify both already-migrated and fresh
  database paths.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `mcp-capabilities`: clean stored references to the retired GitHub catalog entry.

## Impact

Control-plane Alembic migration and its tests, MCP capability spec, and existing
operator migration note. Existing agents referencing GitHub must run the updated
cleanup before they can run without this missing-capability error. No API or
runtime change is needed. All changes remain local and uncommitted.
