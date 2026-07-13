# RFC — KPI Analytics: Request Middleware, OpenSearch Metrics, and In-App Dashboards

## Status

Draft

## Authors

Florian Muller

## Task ID

OBSERV-02

## Version

v2

---

## 1. Context and Motivation

The Fred platform is regularly asked to provide usage metrics to management: how
many users are active, which teams use the platform, which agents are most used,
how much LLM capacity is consumed. Today, answering these questions requires
manually aggregating data from Grafana, MinIO, PostgreSQL, and other sources —
a slow and error-prone process that produces numbers with inconsistent definitions.

The root cause is that Fred's existing observability stack is built for **operational
health** (latency, error rates, infrastructure load) rather than **product
analytics**. Prometheus, the current primary sink, is the right tool for the former
but cannot support the latter: it has no concept of user identity, team membership,
or business-level aggregations.

This RFC proposes a simple, consolidated analytics dashboard — visible to admins,
team owners, and individual users according to their role — that answers the
recurring management questions directly from the application, without manual
aggregation.

The OpenSearch KPI store already exists in Fred and is the right foundation: it
stores full-context events (user, team, agent) and supports the aggregations needed
for product analytics. Two gaps remain before the dashboard is possible:

1. **Missing metrics.** Some key product metrics (e.g. active users) are not
   currently emitted anywhere and need new instrumentation.
2. **No query surface.** There is no in-app endpoint serving shaped, role-scoped
   analytics to the frontend.

Section 3 inventories the required metrics and how each will be sourced. Sections
2 and 4 cover the query endpoint and dashboard.

**Deployment topology note.** Fred has no monolithic agentic backend. The control
plane (`fred-control-plane`) is the central product API. Pod agents are independent
services built on `fred-runtime` (e.g. `fred-agents`); the frontend contacts them
directly using addresses provided by the control plane. The middleware must therefore
be deployed in all user-facing backends independently.

---

## 2. Proposed Solution

Four coordinated changes, implementable independently:

### 2.1 — Required Metrics and How to Source Them

The minimum priority is to provide answers to the recurring management questions
listed below. These are currently answered by manual aggregation across Grafana,
MinIO, and PostgreSQL — the goal is to make them available in one place, in the
app, without manual work.

For each metric: current availability, the code location if already instrumented,
and the action required.

#### Users

| Metric | Current status | Code location | Action |
|--------|----------------|---------------|--------|
| Active users by day | **Missing** | — | Add HTTP middleware (§2.2) |
| Concurrent users (sliding window) | **Missing** | — | Add HTTP middleware (§2.2) |

#### Conversations and Messages
[](../../../apps/control-plane-backend/control_plane_backend/product/service.py)

| Metric | Current status | Code location | Action |
|--------|----------------|---------------|--------|
| New conversations (sessions) by day | **Missing** | Session creation exists at [product/service.py:1659](../../../apps/control-plane-backend/control_plane_backend/product/service.py#L1659) but emits no KPI | Add `kpi.count("session.created_total")` at session creation |
| Messages sent to agents | **Partial** | Each agent turn emits `agent.turn_completed` at [agent_app.py:1619](../../../libs/fred-runtime/fred_runtime/app/agent_app.py#L1619) with `team_id`, `template_agent_id`, `input_tokens`, `output_tokens` | Rename or alias as "messages" in preset; verify `user_id` is included in dims (currently emitted as `KPIActor(type="system")` — no user attribution) |
| Conversations in team vs personal space | **Missing** | Session creation at [product/service.py:1659](../../../apps/control-plane-backend/control_plane_backend/product/service.py#L1659) has `scope_type` context | Add `scope_type` dim (`"team"` / `"personal"`) to `session.created_total` |
| Top N teams by conversation count | **Missing** | — | Derived from `session.created_total` grouped by `team_id` once session KPI is added |

#### Agents

| Metric | Current status | Code location | Action |
|--------|----------------|---------------|--------|
| Number of agents created | **Missing** | Agent creation endpoint exists in control-plane but emits no KPI | Add `kpi.count("agent.created_total")` with `agent_type`, `team_id`, `user_id` dims |
| Distribution of system prompt length | **Missing** | System prompt is resolved at [agent_app.py:892](../../../libs/fred-runtime/fred_runtime/app/agent_app.py#L892) | Add `kpi.gauge("agent.system_prompt_chars")` at agent startup |
| Top N agents by conversation count | **Partial** | `agent.turn_completed` at [agent_app.py:1619](../../../libs/fred-runtime/fred_runtime/app/agent_app.py#L1619) carries `template_agent_id` | Derivable from `agent.turn_completed` grouped by `template_agent_id` — no new instrumentation needed |

#### Resources

| Metric | Current status | Code location | Action |
|--------|----------------|---------------|--------|
| Number of resources currently uploaded | **Partial** | `current_resources_storage_size` tracked in Postgres at [teams/system.py:46](../../../apps/control-plane-backend/control_plane_backend/teams/system.py#L46) and [teams/service.py:668](../../../apps/control-plane-backend/control_plane_backend/teams/service.py#L668) | Query Postgres directly in the preset — no KPI event needed for a current-state gauge |
| Total size of resources uploaded (GB) | **Partial** | Same Postgres field as above | Same as above — aggregate `current_resources_storage_size` across all teams |

**Note on resources:** resource count and size are current-state gauges (not
cumulative counters), so querying Postgres directly in the preset is more accurate
than aggregating KPI events. The preset endpoint can mix OpenSearch and Postgres
sources — this is an implementation detail invisible to the frontend.

### 2.2 — KPI Middleware (replaces `prometheus_fastapi_instrumentator`)

A FastAPI middleware, implemented once in `fred-core` and mounted in all
user-facing backends, that fires on every request and:

- Emits `api.request_latency_ms` via `KPIWriter`.
- The `PrometheusKPIStore` strips high-cardinality dims before Prometheus (existing
  behavior — no change needed).
- The OpenSearch delegate receives the full event including `user_id`.

**Backends that receive the middleware:**

| Backend | Rationale |
|---------|-----------|
| `fred-control-plane` | Primary product API — sessions, teams, agents lifecycle |
| `knowledge-flow-backend` | Document ingestion and RAG — user-facing |
| Pod agents (e.g. `fred-agents`) | Directly called by the frontend; their request volume is user activity |

**Dims emitted per request:**

| Dim | Source | Notes |
|-----|--------|-------|
| `user_id` | JWT `sub` claim via `request.state.user` | Empty string if unauthenticated |
| `route` | `request.scope["route"].path` | Templated path, not raw URL |
| `method` | `request.method` | |
| `http_status` | Response status code | |
| `latency_ms` | `perf_counter` delta | |

`groups` (team names from the JWT) is **not** emitted by the middleware.
Team names are mutable — they can be renamed and cannot be used directly
in ReBAC checks which operate on stable IDs. Team context belongs exclusively
at domain-level `KPIWriter` call sites that already have a stable `team_id`
in scope.

`team_id` is likewise **not** extracted from the request body — body reading
in middleware breaks streaming endpoints (SSE, file uploads).

`prometheus_fastapi_instrumentator` is removed from all backends once the
middleware is in place.

### 2.3 — Analytics Query Endpoint (preset-based)

The preset registry and query endpoint live in `fred-control-plane`. This is
the natural home: it is the central product API, already aware of the full
resource graph (teams, agents, users), and already connected to OpenFGA for
authorization. All backends write KPI events to the same shared OpenSearch
index — the control plane queries that index on behalf of all of them.

A new endpoint: `GET /api/kpi/query?preset=<name>&from=<date>&to=<date>`

**Design principles:**

- The backend owns all query logic. The client sends only: preset name + safe
  typed parameters (date range, optional granularity).
- The authorization scope is injected server-side and cannot be influenced by
  the client (see §2.3).
- The response is shaped data (`[{date, value}]`, `[{label, count}]`) — not
  raw OpenSearch response objects.
- Presets are an explicit allow-list; unknown presets return 400.
- New presets are added by extending the registry — no endpoint changes needed.

**Initial preset set:**

| Preset | Description | Required permission |
|--------|-------------|-------------------|
| `active_users_by_day` | Distinct user count per day | org `admin` |
| `concurrent_users` | Distinct users per 15-min bucket | org `admin` |
| `requests_by_team` | Request volume grouped by team | org `admin` |
| `top_agents` | Most-used agents by request count | org `admin` |
| `team_token_usage` | LLM token consumption per team | team `owner` or `manager` |
| `team_agent_usage` | Request count per agent within a team | team `owner` or `manager` |
| `user_token_usage` | LLM token consumption for the requesting user | any authenticated user |

### 2.4 — Authorization via ReBAC (OpenFGA)

The endpoint resolves the requesting user's scope from OpenFGA before building
the OpenSearch query. The scope is a mandatory filter injected into the query
— it is not a parameter the client controls.

```
Admin presets (active_users_by_day, concurrent_users, requests_by_team, top_agents):
  Check(user, admin, organization) → allow, no scope filter on user/team

Team-scoped presets (team_token_usage, team_agent_usage):
  teams = ListObjects(user, owner|manager, team)
  inject: WHERE dims.team_id IN teams

User-scoped presets (user_token_usage):
  inject: WHERE dims.user_id = requesting_user.uid  (no OpenFGA call needed)
```

A user who is not an org admin receives 403 for admin presets. For team presets,
a user with no owned/managed teams receives an empty result set.

### 2.5 — Frontend Dashboards

Three dashboard pages are planned, gated by role. They share a common
`<KpiChart>` component that calls the preset endpoint and renders the result.

**Page 1 — Platform dashboard (org admins only)**
Priority: highest — this is the dashboard requested by management.

Charts:
- Active users by day (line chart) — preset `active_users_by_day`
- Concurrent users through the day (line chart) — preset `concurrent_users`
- Request volume by team (bar chart) — preset `requests_by_team`
- Top agents by usage (bar chart) — preset `top_agents`

**Page 2 — Team dashboard (team owners and managers)**
Visible only for teams the user owns or manages. Team selector if the user
owns multiple teams.

Charts:
- Token consumption over time — preset `team_token_usage`
- Agent usage within the team — preset `team_agent_usage`

**Page 3 — Personal dashboard (all authenticated users)** — *in progress,
see `docs/swift/backlog/BACKLOG.md` §7b (OBSERV-02)*
Each user can see their own consumption: how much they're using the
platform, and which agents/models are driving that usage. Reachable from
a new icon on the personal-space banner (the banner never shows an icon
today — the existing gear/settings icon is gated on a team-admin
permission the personal space never grants).

Charts:
- My token usage over time — preset `user_token_usage_over_time`
- My token usage by agent — preset `user_token_usage_by_agent`
- My token usage by model — preset `user_token_usage_by_model`

All three reuse the `agent.turn_completed` KPI event (§7.4 of
`BACKLOG.md`'s Phase 7), already emitted per turn with `dims.user_id`,
`dims.agent_instance_name`, `dims.model_name`, and
`quantities.input_tokens`/`output_tokens` — no new instrumentation is
required. Preset names were split one-per-widget instead of the single
`user_token_usage` originally sketched here, to match the convention
already used by the implemented Page 1 presets (`sessions_over_time`,
`top_agents_by_conversations`, etc.).

**Implementation note (2026-07-12):** Page 1 shipped as `AnalyticsPage`
(`/admin/analytics`, gated on `can_observe_platform` per
`docs/swift/platform/REBAC.md` AUTHZ-05 item 16) but diverges from this
RFC in two ways not yet reconciled here: preset names differ from §2.3's
table (e.g. `active_users_over_time` not `active_users_by_day`), and
authorization is enforced per-preset inside each handler
(`kpi/presets/*.py`) rather than via the router-level OpenFGA scope
resolution described in §2.4. Page 2 (team dashboard) remains unbuilt.

**Future (out of scope for this RFC):** if agents become publishable to a
marketplace, a per-agent publisher dashboard would reuse the same preset
infrastructure with agent-scoped presets.

### 2.6 — Caching strategy (no Redis)

With multiple replicas and no shared cache, per-replica in-process caches
produce inconsistent results across page refreshes. The chosen strategy
avoids this:

- **No server-side cache.** Analytics queries are served directly from
  OpenSearch on every request.
- **OpenSearch as the cache.** OpenSearch keeps hot query results in its
  request cache (enabled by default for aggregations on static time ranges).
  A query for "active users yesterday" hits the same shard data on every
  replica — OpenSearch returns the same result regardless of which backend
  replica handles the request.
- **Client-side TTL.** The frontend caches the response for a configurable
  TTL (e.g. 5 minutes) and does not re-fetch on every render. This is
  sufficient for analytics data that does not need to be real-time.
- **Date range design.** Preset parameters use closed time ranges (`from`/`to`).
  "Today so far" queries are inherently live and do not benefit from caching
  — this is acceptable and expected behavior.

This approach gives consistent results across replicas with zero infrastructure
additions.

---

## 3. Alternatives Considered

**Pass raw OpenSearch queries from the frontend.**
Rejected. Exposes storage internals, cannot enforce authorization scope, and
allows clients to run arbitrary expensive aggregations.

**Redis for shared cache.**
Rejected for this RFC. Adds an infrastructure dependency. OpenSearch's own
request cache is sufficient for the defined use cases. Redis can be
reconsidered if sub-second freshness becomes a requirement.

**Preset registry in `fred-core` shared across all backends.**
Rejected.Distributing query endpoints across backends
would duplicate authorization logic and split the API surface.

**Keycloak event log for login counts.**
Rejected as primary source. The backend never observes login events — only
subsequent API calls. The middleware "active user = made at least one API
call" definition is honest and sufficient for the stated need.

---

## 4. Impact on Existing Contracts

| Contract | Change |
|----------|--------|
| `RUNTIME-EXECUTION-CONTRACT.md` | No change — middleware is transport-level |
| `CONTROL-PLANE-PRODUCT-CONTRACT.md` | New `GET /api/kpi/query` endpoint family to be added |
| `PrometheusKPIStore` | No change — existing label filtering already handles high-cardinality dims |
| `KPIWriter` | No change — middleware uses existing `api_call()` helper |
| `prometheus_fastapi_instrumentator` | Removed from all user-facing backends once middleware is deployed |
