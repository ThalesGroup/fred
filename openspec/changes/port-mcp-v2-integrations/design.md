## Context

See `proposal.md` for motivation and `specs/mcp-capabilities/spec.md` for the observable contract. Fred currently wraps `langchain-mcp-adapters.MultiServerMCPClient` in `mcp_utils.py` and `mcp_runtime.py`. Its tool interceptors refresh person credentials, reject ended delegation, and convert receiver refusals into authority loss. Knowledge Flow projects tagged FastAPI routes with `fastapi-mcp`, subclasses its private tool executor for delegated calls, and patches its HTTP session manager to be stateless. These private interfaces are not a safe MCP v2 migration surface.

The SDK v2 protocol removes the HTTP session requirement. FastMCP 4 supports SDK v2 and negotiates with older protocol peers. The first-party `langchain.mcp.MCPAdapter` is beta and removes the old tool-interceptor hook; `fastapi-mcp` does not yet support SDK v2. The current catalog accepts `sse` and `websocket` values, but Fred's connection builder raises `UnsupportedTransportError` for both. Only `streamable_http` and `stdio` are implemented.

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

### Use a Fred-owned client tool bridge over FastMCP 4

Use the stable FastMCP 4 client for MCP transport and protocol negotiation, with a small Fred-owned wrapper that exposes MCP tools as the existing LangChain `BaseTool` objects. Open a call-scoped client/transport for each invocation so the current person token or delegated grant is resolved at call time. Keep discovery caching only for metadata; do not cache live credentials or mutable interceptors across runs. Map MCP `is_error`, structured content, transport exceptions, and tool metadata to the existing Fred tool contract. Preserve origin confinement and no-redirect behavior in the HTTP transport configuration.

Alternative: `langchain.mcp.MCPAdapter` is the official LangChain replacement, but its beta API and removal of per-call tool interceptors do not directly meet Fred's credential and delegation needs. A Fred-owned bridge keeps those checks in one place. Reconsider the adapter once it offers a stable extension point for these policies.

### Replace the Knowledge Flow server bridge with FastMCP 4

Use FastMCP 4's OpenAPI projection to source tools from the existing tagged FastAPI routes. Wrap its tool execution at a Fred-owned boundary so the verified grant and request context are applied to the inner route call, and preserve the current curated error/result mapping. Mount a stateless MCP HTTP app at each existing Knowledge Flow path. Compare generated names, descriptions, input schemas, and enabled-server sets against the current projection before switching it on. Remove the `fastapi-mcp` monkey patch and dependency only after those checks pass.

Alternative: wait for `fastapi-mcp` to release v2 support. Its upstream v2 issue remains open, and the existing private subclass/patch would still need a port. FastMCP 4 has current protocol support and an OpenAPI provider, although Fred must explicitly preserve its FastAPI authorization semantics.

### Preserve the current catalog contract

Map `streamable_http` to FastMCP's HTTP client and `stdio` to its subprocess client. Keep `sse` and `websocket` accepted by catalog validation and rejected by the runtime with the existing typed error until a separately approved public-contract change. Do not silently reinterpret a websocket URL as HTTP. No data migration is required.

Alternative: remove unsupported values from the SDK model now. That would make persisted external catalogs fail validation and would alter the durable `mcp-capabilities` requirement, so it is outside this compatibility change.

## Risks / Trade-offs

- [OpenAPI projection drift] -> Capture the current Knowledge Flow tool names, descriptions, and input schemas, then compare with the new provider and explicitly adapt differences before cutover.
- [Security context lost between MCP and inner FastAPI request] -> Exercise user-token and delegated calls end to end, including refusal, redirect, stale grant, and multi-pod routing cases.
- [Extra client setup latency per tool call] -> Keep tool metadata cached without secrets, measure call latency against the current path, and reuse only safe transport infrastructure.
- [FastMCP 4 / SDK v2 dependency churn] -> Pin compatible versions in each affected package and update lockfiles in one reviewable change.
- [Legacy remote peers] -> Test v2-to-v2 and current legacy-protocol interoperability for the HTTP paths before release.

## Migration Plan

1. Build the client bridge and server projection behind the existing Fred MCP interfaces, with targeted parity tests against current behavior.
2. Move all affected package constraints and lockfiles together, remove v1-only dependencies and patches, and update deployment notes.
3. Run focused integration tests, root quality checks, an independent read-only branch review, and a staged client/server smoke test before marking the draft PR ready.
4. Roll back by deploying the previous image set and lockfile state; existing catalog entries and mount paths require no data reversal.

## Open Questions

None. The review of this proposal is the decision point for the client bridge and Knowledge Flow projection approach.
