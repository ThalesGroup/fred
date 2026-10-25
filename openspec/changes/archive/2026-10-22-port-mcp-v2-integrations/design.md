## Context

See `proposal.md` for motivation and `specs/mcp-capabilities/spec.md` for the observable contract. Fred currently wraps `langchain-mcp-adapters.MultiServerMCPClient` in `mcp_utils.py` and `mcp_runtime.py`. Its tool interceptors refresh person credentials, reject ended delegation, and convert receiver refusals into authority loss. Knowledge Flow projects tagged FastAPI routes with `fastapi-mcp`, subclasses its private tool executor for delegated calls, and patches its HTTP session manager to be stateless. These private interfaces are not a safe MCP v2 migration surface.

The SDK v2 protocol removes the HTTP session requirement. FastMCP 4 supports SDK v2 and negotiates with older protocol peers. LangChain's first-party `langchain.mcp.MCPAdapter` uses FastMCP 4 and replaces the v1-only `langchain-mcp-adapters` package. `fastapi-mcp` does not yet support SDK v2. The current catalog accepts `sse` and `websocket` values, but Fred's connection builder raises `UnsupportedTransportError` for both. Only `streamable_http` and `stdio` are implemented.

## Goals / Non-Goals

**Goals:**

- Keep Fred's own security and error decisions at the MCP call boundary, independent of changes in third-party adapter internals.
- Keep Knowledge Flow's curated OpenAPI-to-tool projection, mount paths, and auth checks while switching the MCP transport and protocol implementation.
- Verify protocol negotiation and stateless behavior with actual client/server exchanges, rather than import-only checks.

**Non-Goals:**

- Implement elicitation, subscriptions, background tasks, prompts, or resources.
- Add `sse` or `websocket` execution to Fred's catalog runtime; retain their current validation and explicit unsupported outcome pending a separate contract decision.
- Change MCP catalog storage, agent selection, or database tables.

## Decisions

### Use LangChain's first-party MCPAdapter

Use `langchain.mcp.MCPAdapter` to discover tools and convert them to LangChain `BaseTool` objects. Pass configured FastMCP clients or transports to its public target API. Keep Fred's credential refresh, delegation, and authority decisions in transport authentication and the existing agent tool boundary. Do not implement a Fred-owned MCP-to-LangChain tool wrapper or protocol adapter. Keep each run's credentials isolated; use supported caching only where it cannot share authority between users or runs. Preserve origin confinement and no-redirect behavior in the HTTP transport configuration.

The adapter API is beta, so pin and test a known version. Its removal of MCP-specific tool interceptors means Fred must use supported transport auth and existing agent tool handling instead of importing private adapter types.

### Replace the Knowledge Flow server bridge with FastMCP 4

Use FastMCP 4's `from_fastapi` integration, backed by its OpenAPI provider, to source tools from the existing tagged routes. Its public route maps select the same tool sets. Use ordinary ASGI authentication and request context propagation around the mounted server so the verified grant reaches the inner route. Do not implement MCP request handling or tool conversion. Mount a stateless MCP HTTP app at each existing Knowledge Flow path and combine its lifespan with the existing app lifespan. Compare generated names, descriptions, input schemas, and enabled-server sets against the current projection before switching it on. Remove the `fastapi-mcp` monkey patch and dependency only after those checks pass.

Alternative: wait for `fastapi-mcp` to release v2 support. Its upstream v2 issue remains open, and the existing private subclass/patch would still need a port. FastMCP 4 has current protocol support and an OpenAPI provider, although Fred must explicitly preserve its FastAPI authorization semantics.

### Preserve the current catalog contract

Map `streamable_http` to FastMCP's HTTP client and `stdio` to its subprocess client. Keep `sse` and `websocket` accepted by catalog validation and rejected by the runtime with the existing typed error until a separately approved public-contract change. Do not silently reinterpret a websocket URL as HTTP. No data migration is required.

Alternative: remove unsupported values from the SDK model now. That would make persisted external catalogs fail validation and would alter the durable `mcp-capabilities` requirement, so it is outside this compatibility change.

## Risks / Trade-offs

- [OpenAPI projection drift] -> Capture the current Knowledge Flow tool names, descriptions, and input schemas, then compare with the new provider and explicitly adapt differences before cutover.
- [Security context lost between MCP and inner FastAPI request] -> Exercise user-token and delegated calls end to end, including refusal, redirect, stale grant, and multi-pod routing cases.
- [Extra client setup latency per turn] -> Cache protocol responses through the SDK only for a fixed credential partition. Fresh adapters still discover legacy peers on each turn; keep the earlier benchmark as historical evidence and measure this residual cost before optimizing it further.
- [FastMCP 4 / SDK v2 dependency churn] -> Pin compatible versions in each affected package and update lockfiles in one reviewable change.
- [Legacy remote peers] -> Test v2-to-v2 and current legacy-protocol interoperability for the HTTP paths before release.

## Migration Plan

1. Adopt MCPAdapter and the FastMCP OpenAPI provider, with targeted parity tests against current behavior.
2. Move all affected package constraints and lockfiles together, remove v1-only dependencies and patches, and update deployment notes.
3. Run focused integration tests, root quality checks, an independent read-only branch review, and a staged client/server smoke test before marking the draft PR ready.
4. Roll back by deploying the previous image set and lockfile state; existing catalog entries and mount paths require no data reversal.

## Open Questions

None. The developer selected the maintained upstream adapter instead of a Fred-owned tool bridge.
