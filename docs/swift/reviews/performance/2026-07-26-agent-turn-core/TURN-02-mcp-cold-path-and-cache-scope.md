# TURN-02 — MCP cold discovery is sequential, token-scoped, pod-local, and not singleflight

- **GitHub issue:** dedicated issue not yet created
- **Priority:** P1
- **Verdict:** needs-load-test
- **Owner:** unassigned

## Production impact

Every turn creates a new MCP provider and activates it before building the
executor. A cache hit avoids discovery, but the key includes the raw access
token and the cache lives in one pod for five minutes. A cold wave across many
users or four replicas therefore shares little work.

On a miss, configured servers are discovered sequentially. The cache lock is
released before discovery, so concurrent misses for the same key can perform
duplicate work. For 200 distinct user tokens and seven servers, a fully cold
wave can attempt up to 1,400 server discovery calls before LLM execution on
each affected pod.

## Evidence

- `libs/fred-runtime/fred_runtime/app/agent_app.py:751-754` creates a
  `FredMcpToolProvider` per turn.
- `libs/fred-runtime/fred_runtime/react/react_runtime.py:641-651` awaits
  provider activation before the executor can run.
- `libs/fred-runtime/fred_runtime/common/mcp_runtime.py:78-88` defines a
  five-minute process-local cache keyed by agent, servers, and raw access token.
- `mcp_runtime.py:117-145` checks under a lock, connects outside it, then
  inserts; there is no in-flight/singleflight entry.
- `libs/fred-runtime/fred_runtime/common/mcp_utils.py:278-306` awaits
  `client.get_tools` sequentially for every configured server.
- The source comment in `mcp_runtime.py:48-58` records a prior observed cost of
  about 2–3 seconds for seven servers; this audit did not reproduce that
  benchmark.

## Minimal fix direction

First instrument cache hit/miss, discovery wall time, server count, and failure
count with bounded labels. Then parallelize independent server discovery with
bounded concurrency and aggregate errors. Add singleflight per cache key. Any
change to the token-scoped key must receive a security review; do not share
authenticated tool clients across principals merely for speed.

## Acceptance criteria

- Concurrent misses for the same key perform one discovery operation.
- Independent servers are discovered concurrently under an explicit bound.
- Cache scope, TTL, token handling, replica locality, and invalidation are
  documented and tested.
- Raw bearer tokens are not retained as ordinary dictionary keys.
- Cold and warm 200-turn tests report time to first token, MCP request count,
  hit ratio, memory, and failures across four replicas.

## Decision log

- **2026-07-26:** scaling shape confirmed; operational severity remains
  `needs-load-test`.

## Resolution evidence

Not resolved.
