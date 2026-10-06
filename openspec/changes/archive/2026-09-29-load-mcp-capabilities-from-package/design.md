## Context

See proposal.md for the agreed scope. Native capability discovery accepts one
class or instance per `fred.capabilities` entry point. MCP transport also needs
the catalog's disabled servers and connection settings before app construction.

## Goals / Non-Goals

Keep one resolved server list for transport and capability registration. Keep
the runtime independent of concrete capability packages. Do not migrate live
MCP clients, transport, auth, or prompt rendering into the SDK.

## Decisions

- Move `McpCapability`, its configuration/prompt types and builders to
  `fred_sdk.contracts.capability.mcp`. Retain the old runtime import as a thin
  compatibility re-export. Registration uses a structural registry protocol.
- Move YAML validation and instruction-resource resolution to
  `fred_sdk.resources.mcp`. Expose file and packaged-resource loaders returning
  a typed catalog with the existing `servers`/`get_server` interface.
- Add `fred.mcp_catalogs` entry points for zero-argument catalog loaders.
  `fred-capability-mcp` exports a loader using SDK resources. This preserves
  the existing native registration contract and makes all server metadata
  available to transport before capabilities are built.
- Runtime bootstrap selects an explicit `FRED_MCP_CATALOG_FILE`, otherwise an
  existing `./config/mcp_catalog.yaml`, otherwise installed catalog providers.
  A selected file fully replaces packaged catalogs (including an empty file
  catalog); no merge resurrects disabled/removed servers. Preserve the current
  no-MCP behavior for an explicitly selected missing file.
- Merge installed catalogs deterministically; fail on duplicate server IDs,
  provider failures or invalid provider returns. Missing providers yield no MCP.
- Remove the pod's compatibility symlink and image catalog copy, so the default
  pod actually uses package discovery. Helm keeps supplying its external catalog.

Worktree port rewriting follows the catalog into its package. The diagnostic
assistant’s explicit configuration reload runs in a worker thread, so invoking
installed providers does not block the request event loop. Ordinary agent turns
reuse the startup configuration.

## Risks / Trade-offs

- Registry and transport drift → both use the same resolved catalog.
- Wheel resources versus checkout paths → use importlib resources and test a wheel.
- Import layering regression → SDK-only tests reject runtime imports.
- New default on pods installing the package → document precedence and preserve
  external files; pods without the package remain empty.

## Migration Plan

Deploy matching image/chart normally. Custom catalogs retain their existing path
override. Roll back image/chart together; no stored-data migration is required.
