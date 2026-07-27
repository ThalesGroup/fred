# TURN-01 — runtime binding fans one turn out to about 21 control-plane ReBAC operations

- **GitHub issue:** dedicated issue not yet created
- **Priority:** P1
- **Verdict:** confirmed
- **Owner:** unassigned

## Production impact

Before runtime activation or the first LLM token, the pod calls the control
plane to resolve the managed agent instance. That internal route authorizes the
request by constructing the complete `TeamWithPermissions` product projection,
although the route only needs a read decision and the instance binding.

For a regular user, one resolution performs approximately 21 OpenFGA operations:
one required permission check, two membership-enrichment lookups, fourteen
permission checks, and four role lookups. It also repeats team metadata work and
may resolve user summaries through the identity service. At 200 concurrent
turns, that shape is roughly 4,200 control-plane OpenFGA operations before LLM
execution.

## Exact call chain

```text
POST /agents/execute/stream
  -> _authorize_and_resolve
    -> _resolve_agent_instance
      -> fresh httpx.AsyncClient
      -> GET control-plane /internal/.../runtime-binding
        -> get_team_by_id_from_service
          -> _validate_team_and_check_permission
          -> _enrich_teams_with_membership
          -> _get_team_permissions_for_user
          -> _get_user_roles_in_team
          -> retention metadata
        -> agent instance read
        -> team capability settings read
```

## Evidence

- `libs/fred-runtime/fred_runtime/app/agent_app.py:1242-1248` creates a new
  `httpx.AsyncClient(timeout=10.0)` for each managed resolution.
- `apps/control-plane-backend/control_plane_backend/product/api.py:913-954`
  resolves the internal binding and calls `get_team_by_id_from_service` only to
  establish authorization.
- `apps/control-plane-backend/control_plane_backend/teams/service.py:472-530`
  constructs the full team projection.
- `teams/service.py:1356-1408` performs the required permission check and team
  metadata read.
- `teams/service.py:1135-1223` performs two concurrent OpenFGA membership
  lookups and may resolve user summaries.
- `teams/service.py:1260-1283` checks every `TeamPermission`;
  `libs/fred-core/fred_core/security/rebac/rebac_engine.py:139-165` declares
  fourteen team permissions.
- `teams/service.py:1438-1481` obtains four role relations.

## Minimal fix direction

Give the internal runtime-binding route a narrow authorization/query path:
perform exactly the required `CAN_READ` decision, then fetch the scoped agent
instance and capability settings. Do not construct a team product DTO. Reuse a
process-wide async control-plane client from the runtime pod.

## Acceptance criteria

- One managed binding has an explicit, tested remote-call budget.
- Authorization remains fail-closed and equivalent for personal,
  collaborative, and service-agent contexts.
- The route does not load membership lists, every team permission, or role
  summaries.
- The runtime reuses a shared async HTTP client with an explicit timeout.
- A 200-turn test records binding p50/p95/p99, OpenFGA request rate/errors, and
  time to first LLM token.

## Decision log

- **2026-07-26:** recorded P1 confirmed. The remote-call fan-out is statically
  established; its production latency still needs measurement.

## Resolution evidence

Not resolved.
