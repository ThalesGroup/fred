## Why

Fred pins the Python MCP SDK below v2 because its LangChain client adapter and Knowledge Flow server integration use v1-only APIs. A dependency update already demonstrated that lifting the pin alone breaks imports and startup. Fred needs an explicit client and server migration before MCP v2 can be installed safely.

## What Changes

- Replace the v1-only MCP client adapter and server integration with v2-compatible integrations, then update constraints and lockfiles together.
- Preserve tool discovery and calls, Knowledge Flow's existing MCP endpoints and projected tools, user and delegated authorization, authority-loss behavior, and stateless HTTP across pods.
- Cover the current `streamable_http` and `stdio` runtime paths, and document the existing `sse` and `websocket` configuration paths. Any change to their accepted configuration requires explicit scope review.
- Add focused interoperability, security, and regression tests, plus deployment migration notes.
- Keep new MCP v2 product features, including elicitation and subscriptions, outside this compatibility change.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `mcp-capabilities`: Specify MCP v2 client and Knowledge Flow server interoperability while retaining existing MCP catalog, tool, and authorization contracts.

## Impact

- Runtime MCP connection, lifecycle, tool wrapping, auth refresh, and delegation modules in `libs/fred-runtime`.
- Knowledge Flow MCP mounts and its FastAPI delegation bridge in `apps/knowledge-flow-backend` and `libs/fred-core`.
- MCP dependency declarations and lockfiles in the runtime, core, SDK, and Knowledge Flow packages; tests and deployment documentation.
- No planned database schema or API endpoint change.

Tracking: https://github.com/ThalesGroup/fred/issues/3217
