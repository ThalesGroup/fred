## Why

The MCP catalog and instruction files now belong to `fred-capability-mcp`, but
their loader and `McpCapability` still belong to the runtime. Following the
developer's refinement of [issue 2708](https://github.com/ThalesGroup/fred/issues/2708),
the package must supply its catalog through SDK primitives when installed.

## What Changes

- Move MCP capability construction, prompt grouping, composer controls and catalog
  parsing into `fred-sdk`, without importing the runtime.
- Let installed packages contribute MCP catalogs at pod startup; install
  `fred-capability-mcp` to supply the existing servers and packaged instructions.
- Preserve external catalog overrides, server IDs, enabled flags, team policies,
  stored configuration and prompt contents.
- Keep live MCP transport and execution integration in `fred-runtime`.

## Capabilities

### New Capabilities

- `mcp-capabilities`: SDK authoring and installed-catalog discovery for MCP capabilities.

### Modified Capabilities

None.

## Impact

SDK capability/resource modules, runtime catalog bootstrap and import sites,
`fred-capability-mcp`, pod packaging, tests and operational documentation.
No API or database migration.
