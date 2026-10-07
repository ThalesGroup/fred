## Why

The default Fred pod now discovers its internal MCP servers from installed
capabilities. A deployment cannot add a third-party server through its own
catalog without replacing that internal set. The developer requested an
additive external catalog in `fred-agents` for this reviewable slice of
[issue 2708](https://github.com/ThalesGroup/fred/issues/2708).

## What Changes

- Load an optional `mcp_catalog_external.yaml` after installed MCP providers and
  combine their servers into one validated catalog.
- Put the external file in `apps/fred-agents/config` and expose its contents as
  `applications.fred-agents.mcp_catalog_external` in the Fred chart.
- Keep the existing `FRED_MCP_CATALOG_FILE` whole-catalog replacement behavior
  for compatibility; duplicate IDs between providers and the additive file fail.

## Capabilities

### Modified Capabilities

- `mcp-capabilities`: deployment-owned MCPs can augment installed providers.

## Impact

Runtime catalog bootstrap, the Fred pod's config/image, Helm values and schema,
tests, and operational documentation. No API or database migration.
