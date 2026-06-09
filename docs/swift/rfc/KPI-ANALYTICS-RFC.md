# RFC — KPI Analytics: Request Middleware, OpenSearch Metrics, and In-App Dashboards

## Status

Draft

## Authors

Florian Muller

## Task ID

OBSERV-02

## Version

v1

---

## 1. Context and Motivation

Fred currently uses `prometheus_fastapi_instrumentator` for HTTP-level metrics and
a `KPIWriter` abstraction for domain events. Both write to Prometheus, which is
appropriate for operational health (latency, error rates) but structurally unsuitable
for product analytics:

- Prometheus cannot carry high-cardinality labels such as `user_id` or `agent_id`
  without causing cardinality explosion.
- There is no way to answer "how many distinct users were active today?" or "which
  teams use agent X the most?" from Prometheus data.
- Management and team owners have no in-app visibility into usage metrics — they
  must rely on OpenSearch Dashboards, which is an ops tool not suited for end-users.

The OpenSearch KPI store already exists (`PrometheusKPIStore` with an OpenSearch
delegate) and already receives full-dim events. The gaps are:

1. No middleware emitting per-request events with user identity.
2. No in-app query endpoint serving preset analytics to the frontend.
3. No authorization model scoping analytics queries per user role.

---

## 2. Proposed Solution

Three coordinated changes, implementable independently:

### 2.1 — KPI Middleware (replaces `prometheus_fastapi_instrumentator`)

A FastAPI middleware added to all backends (agentic-backend, knowledge-flow-backend)
that fires on every request and:

- Emits `api.request_latency_ms` via `KPIWriter` with full dims.
- The `PrometheusKPIStore` strips high-cardinality dims before Prometheus (existing
  behavior — no change needed).
- The OpenSearch delegate receives the full event including `user_id` and `groups`.

Dims emitted per request:

| Dim | Source | Notes |
|-----|--------|-------|
| `user_id` | JWT sub claim via `request.state.user` | Empty string if unauthenticated |
| `groups` | JWT groups claim | Comma-separated team names |
| `route` | `request.scope["route"].path` | Templated path, not raw URL |
| `method` | `request.method` | |
| `http_status` | Response status code | |
| `latency_ms` | perf_counter delta | |

`team_id` is **not** extracted from the request body — body reading in middleware
breaks streaming endpoints (SSE, file uploads). Domain-level dims (agent_id,
team_id, scope) continue to be added at explicit `KPIWriter` call sites.

`prometheus_fastapi_instrumentator` is removed from all backends once the middleware
is in place, as it becomes redundant.

### 2.2 — Analytics Query Endpoint (preset-based)

A new endpoint family, e.g. `GET /api/kpi/query?preset=<name>&from=<date>&to=<date>`,
backed by a preset registry in the backend. The client never sends raw OpenSearch DSL.

**Design principles:**

- The backend owns all query logic. The client sends only: preset name + safe typed
  parameters (date range, optional granularity).
- The authorization scope is injected server-side and cannot be influenced by the
  client (see §2.3).
- The response is shaped data (`[{date, value}]`, `[{label, count}]`) — not raw
  OpenSearch response objects.
- Presets are an explicit allow-list; unknown presets return 400.

**Initial preset set:**

| Preset | Description | Required permission |
|--------|-------------|-------------------|
| `active_users_by_day` | Distinct user count per day | org `admin` |
| `concurrent_users` | Distinct users per 15-min bucket | org `admin` |
| `requests_by_team` | Request volume grouped by team | org `admin` |
| `agent_usage` | Request count per agent | `read` on agent (via OpenFGA) |
| `team_activity` | Active users within a team | team `owner` or `manager` |

New presets are added by extending the registry — no endpoint changes needed.

### 2.3 — Authorization via ReBAC (OpenFGA)

The endpoint resolves the requesting user's scope from OpenFGA before building the
OpenSearch query. The scope is a mandatory filter injected into the query — it is
not a parameter the client controls.

```
Admin preset (active_users_by_day, concurrent_users, requests_by_team):
  Check(user, admin, organization) → allow, no scope filter

Team-scoped preset (team_activity):
  teams = ListObjects(user, owner|manager, team)
  inject: WHERE dims.team_id IN teams

Agent-scoped preset (agent_usage):
  agents = ListObjects(user, read, agent)
  inject: WHERE dims.agent_id IN agents
```

A user who is neither org admin nor owner/manager of any team gets an empty result
set for team/agent presets, and 403 for admin presets.

### 2.4 — Caching strategy (no Redis)

With multiple replicas and no shared cache, per-replica in-process caches produce
inconsistent results across page refreshes. The chosen strategy avoids this:

- **No server-side cache.** Analytics queries are served directly from OpenSearch
  on every request.
- **OpenSearch as the cache.** OpenSearch keeps hot query results in its request
  cache (enabled by default for aggregations on static time ranges). A query for
  "active users yesterday" hits the same shard data on every replica — OpenSearch
  returns the same result regardless of which backend replica handles the request.
- **Client-side TTL.** The frontend caches the response for a configurable TTL
  (e.g. 5 minutes) and does not re-fetch on every render. This is sufficient for
  analytics data that does not need to be real-time.
- **Date range design.** Preset parameters use closed time ranges (`from`/`to`).
  "Today so far" queries are inherently live and do not benefit from caching — this
  is acceptable and expected behavior.

This approach gives consistent results across replicas with zero infrastructure
additions.

---

## 3. Alternatives Considered

**Pass raw OpenSearch queries from the frontend.**
Rejected. Exposes storage internals, cannot enforce authorization scope, and allows
clients to run arbitrary expensive aggregations.

**Redis for shared cache.**
Rejected for this RFC. Adds an infrastructure dependency. OpenSearch's own request
cache is sufficient for the defined use cases. Redis can be reconsidered if
sub-second freshness becomes a requirement.

**Keycloak event log for login counts.**
Rejected as primary source. The backend never observes login events — only
subsequent API calls. The middleware "active user = made at least one API call"
definition is honest and sufficient for the stated need.

**Heartbeat-based time-on-site.**
Out of scope for this RFC. Requires a frontend change (60s heartbeat ping while
tab is focused). The middleware-derived session duration approximation (gap between
first and last request within a 30-min inactivity window) is acknowledged as noisy
and not surfaced as a metric in this RFC.

---

## 4. Impact on Existing Contracts

| Contract | Change |
|----------|--------|
| `RUNTIME-EXECUTION-CONTRACT.md` | No change — middleware is transport-level, not execution-level |
| `CONTROL-PLANE-PRODUCT-CONTRACT.md` | New `/api/kpi/query` endpoint family to be added |
| `PrometheusKPIStore` | No change — existing label filtering already handles high-cardinality dims |
| `KPIWriter` | No change — middleware uses existing `api_call()` helper |
| `prometheus_fastapi_instrumentator` | Removed from all backends once middleware is deployed |

---

## 5. Open Questions

1. **Which backends get the middleware first?** Proposed: agentic-backend only in
   the first iteration, knowledge-flow-backend in a follow-up.
2. **Where does the preset registry live?** Proposed: `fred-core` as a shared
   library so multiple backends can expose the same presets without duplicating
   query logic.
3. **Frontend component scope.** This RFC does not specify the frontend component.
   A separate CHAT or FRONT backlog item should track the admin dashboard UI.
4. **`team_id` dim availability.** The middleware cannot extract `team_id` from
   request bodies. Team-scoped metrics rely on `groups` from the JWT (team names)
   or on domain-level `KPIWriter` call sites that already have team context. The
   mapping between Keycloak group names and OpenFGA team IDs must be verified.
