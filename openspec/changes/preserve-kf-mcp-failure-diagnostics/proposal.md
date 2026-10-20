# Proposal

## Why

A production Excel investigation found four KF description HTTP 404s but could not distinguish dataset resolution from preview failure. `DelegatedFastApiMCP` duplicates upstream tool execution and replaces most inner HTTP errors with `RuntimeError("Tool request failed.")`, losing the original HTTP evidence and upstream failure logging.

## What Changes

- Supply a dedicated `httpx.AsyncClient` through the public `FastApiMCP(http_client=...)` interface. A transport wrapping `ASGITransport` sanitizes reserved delegation values, injects the verified grant and trusted logging context, and the client disables redirects.
- Log completed inner HTTP failures in an async response hook with registered operation metadata, actual status and validated inner request references, independently of traceback formatting.
- Delegate ordinary request mapping, response serialization and tool errors to upstream `FastApiMCP`. Retain only a minimal private execution wrapper that translates a typed authority refusal into the existing `CallToolResult(structuredContent={"cause": "authority_lost"}, isError=True)`.
- Classify tabular dataset-resolution and preview failures with closed reason codes, and explain empty tabular discovery with bounded resolution counts calculated during existing work.
- Preserve HTTP route responses, authorization decisions, admitted context, typed authority stops and the curated SQL 400 detail contract. Ordinary MCP failures regain upstream status/detail reporting; agent-side error presentation remains out of scope.
- Verify the public client/transport path through actual MCP calls, including scope isolation, response readability, lifecycle cleanup and sensitive-data confinement in logs.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `structured-logging`: Retain safe operator evidence for first-party MCP inner failures and tabular resolution outcomes independently of MCP error conversion.

## Impact

The shared first-party MCP integration in `libs/fred-core`, Knowledge Flow MCP construction/lifecycle and tabular code, focused offline tests, the existing observability guide and an operator migration note. Keep `fastapi-mcp==0.4.0`; no package upgrade is required. Ordinary MCP error text changes from the Fred blanket message to upstream status/detail reporting. No new error protocol, configuration, metrics, authorization decision, HTTP route schema or UI change is intended. Traceback formatter work, agent-side logging/presentation changes, retries and a fix for the unconfirmed Excel incident cause are excluded.

Tracking: [#3196](https://github.com/ThalesGroup/fred/issues/3196), follow-up to #2906. The public-interface approach with a minimal authority wrapper was accepted on 2026-10-20. Implementation and the assigned draft PR were authorized by the developer on 2026-10-20.
