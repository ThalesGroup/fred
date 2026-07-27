# TURN-07 — expired-token recovery blocks the event loop with synchronous Keycloak HTTP

- **GitHub issue:** dedicated issue not yet created
- **Priority:** P1
- **Verdict:** confirmed
- **Owner:** unassigned

## Production impact

Knowledge Flow and MCP requests are asynchronous, but their 401 recovery calls
a synchronous refresh callback. The shared refresh helper uses top-level
`httpx.post` with a ten-second timeout. While a token refresh is in flight, the
runtime pod's event-loop thread cannot advance unrelated SSE turns, timers, or
tool calls.

The path is exceptional rather than per-turn, but expirations often occur in
cohorts. A refresh wave can therefore create a pod-wide latency cliff.

## Evidence

- `libs/fred-runtime/fred_runtime/runtime_support/user_token_refresher.py:23-52`
  is synchronous and calls `httpx.post(..., timeout=10.0)`.
- `libs/fred-runtime/fred_runtime/common/kf_base_client.py:223-275` is async but
  invokes `_try_refresh_token()` synchronously after a 401.
- `kf_base_client.py:145-178` directly calls the agent/callback refresh method.
- `libs/fred-runtime/fred_runtime/common/mcp_interceptors.py:35-73` is async but
  calls `self._refresh()` synchronously after an expired-token response.
- `libs/fred-runtime/fred_runtime/app/agent_app.py:454-505` and
  `libs/fred-runtime/fred_runtime/integrations/v2_runtime/adapters.py:1393-1442`
  route runtime adapters to the synchronous helper.

## Minimal fix direction

Provide one async token-refresh service backed by a shared async HTTP client,
explicit timeout, and singleflight per refresh-token/session identity. Make
Knowledge Flow, MCP, and media adapters await it. Avoid merely wrapping every
call in an unbounded thread pool.

## Acceptance criteria

- No synchronous network I/O is reachable from an async execution/tool path.
- Concurrent refreshes for one identity coalesce without sharing tokens across
  principals.
- Refresh timeout/failure remains bounded and fail-closed.
- Logs and metrics expose refresh duration/outcome without tokens or user IDs.
- A delayed-Keycloak test proves unrelated SSE streams continue to progress.

## Decision log

- **2026-07-26:** recorded P1 confirmed. A ten-second timeout bounds the remote
  call but does not prevent event-loop blocking.

## Resolution evidence

Not resolved.
