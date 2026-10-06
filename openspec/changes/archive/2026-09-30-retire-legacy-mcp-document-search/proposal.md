## Why

The legacy `mcp-knowledge-flow-mcp-text` entry duplicates the native
`document_access` capability. Retire its configuration and runtime implementation
as requested in the local work on https://github.com/ThalesGroup/fred/issues/2708.

## What Changes

- Remove the legacy entry from packaged and Helm catalogs, its prompt resource,
  toolkit, built-in factory wiring and obsolete SDK authoring constant.
- Switch ReAct RAG, Mindmap and Comparison defaults to `document_access`, as
  explicitly confirmed by the developer. Keep their existing template identities.
- Add a control-plane Alembic data migration removing only the retired capability
  from stored selections and configuration. Do not auto-enroll the replacement.
- Remove the unimplemented GitHub catalog entry, explicitly approved by the developer.
- Retire the entire `inprocess` MCP transport: SDK contract, runtime
  factory/lifecycle and generated API client. Local tools use native capabilities.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `mcp-capabilities`: retire the legacy document-search server and clean stored references.

## Impact

**BREAKING:** custom templates must replace the retired server/SDK constant with
`document_access`. Existing explicitly selected agents lose only the retired tool
after migration. Shared Knowledge Flow REST clients and the native search adapter
remain available. No database mutation against a running deployment is requested;
verification uses temporary databases.
