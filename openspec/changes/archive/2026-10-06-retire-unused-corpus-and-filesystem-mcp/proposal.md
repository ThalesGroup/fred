## Why

Agent document discovery already uses `list_document_tree`; the packaged corpus and filesystem MCP servers add two selectable, broad tool surfaces without an active agent use case. Removing those surfaces is a focused step toward the convergence tracked in [#2328](https://github.com/ThalesGroup/fred/issues/2328).

## What Changes

- **BREAKING** Stop publishing `/mcp-corpus` and `/mcp-fs` from Knowledge Flow and remove their entries from Fred's packaged MCP catalog and author-facing SDK constants.
- Remove the now-unused MCP filesystem mount flag and its deployment/configuration schema entries, along with tests and current docs that advertise the retired servers.
- Keep Knowledge Flow's underlying HTTP corpus-management and `/fs` routes. PPT Filler and other runtime/UI consumers still use `/fs` directly; this lot does not migrate them or remove stored data.
- Keep `document_access.list_document_tree` and other focused document capabilities unchanged.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `mcp-capabilities`: Retire the two packaged Knowledge Flow MCP server identities while preserving other installed and externally supplied MCP servers.

## Impact

Knowledge Flow MCP mounting and configuration; `fred-capability-mcp` catalog; fred-sdk exports and authoring examples; agent-pod catalog tests; generated configuration schema/chart values. The HTTP `/fs` API and its clients remain in service.
