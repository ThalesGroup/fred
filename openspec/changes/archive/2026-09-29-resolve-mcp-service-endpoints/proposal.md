## Why

The packaged internal MCP catalog repeats Knowledge Flow's URL and port instead
of following the pod's configured address. This continues the locally authorized
MCP extraction tracked by https://github.com/ThalesGroup/fred/issues/2708.

## What Changes

- Declare a typed Fred service and an MCP path in internal catalog entries.
- Define the service-address interface in fred-sdk and implement it in fred-runtime
  using existing pod configuration, including its configured port and API prefix.
- Inject the interface into catalog providers at startup; preserve concrete external URLs.
- Use service references in packaged and Helm internal MCP entries.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `mcp-capabilities`: resolve internal MCP endpoints from configured Fred services.

## Impact

SDK catalog parsing, runtime bootstrap, MCP package, Helm defaults, authoring docs
and worktree URL patching. No network discovery, new configuration source,
McpCapability behavior change or public HTTP schema change.
