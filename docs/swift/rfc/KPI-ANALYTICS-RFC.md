# RFC — KPI Analytics: Request Middleware, OpenSearch Metrics, and In-App Dashboards

## Status

implemented (2026-07-26) — v3's full dev plan (§5) is done: backend B1-B9,
frontend F1-F5. B8/F6 were dropped mid-implementation, no replacement (see
§2.9 correction below). Both §6 sign-off items resolved during implementation
rather than blocking it: the conversation-breakdown dimension shipped with
the RFC's own proposed default (by agent, reusing `top_agents_by_conversations`
— see §2.5 Page 2), and the model-routing fail-closed fallback was confirmed
and implemented as B7 (`AGENT-CAPABILITY-RFC.md` §8.7). Two gaps found and
fixed mid-implementation, not part of the original dev plan: B3/B4 (green/cost
computation) had been silently skipped during the original B1-B7 pass —
implemented now; `storage_by_team`'s platform-wide view was missing the
`can_manage_platform` gate §2.4 specifies — fixed. v1/v2 (§2.1–§2.4, §2.6)
were already implemented and unchanged before this pass. §2.9 corrected
2026-07-25 mid-implementation: the "new platform settings" work it originally
proposed was found to already exist (`max_resources_storage_size`,
`team_delete_grace`/`max_idle`, CTRLP-12) — B8/F6 dropped from the dev plan,
no replacement.

## Authors

Florian Muller (v1–v2). Dimitri Tombroff (v3 — role-based dashboard
finalization, 2026-07-25).

## Task ID

OBSERV-02

## Version

v3

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
or business-level aggregations. **This RFC's dashboards are business/product
analytics only — infrastructure/ops metrics (CPU, memory, cluster health) stay in
Grafana and are explicitly out of scope, v3 included.**

The OpenSearch KPI store already exists in Fred and is the right foundation: it
stores full-context events (user, team, agent) and supports the aggregations needed
for product analytics.

**v3 scope.** v1/v2 built the platform-wide dashboard (`AnalyticsPage`) and the
personal dashboard, and specified but never built the team dashboard ("Page 2 —
remains unbuilt"). Since then, Fred also grew two other pieces of infrastructure
that any dashboard finalization must sit on top of, not duplicate: a mature
per-team **capability enablement system** (`AGENT-CAPABILITY-RFC.md`) and a mature
**task/progress bus** (`TASK-EVENT-STREAM-RFC.md`, OPS-04). v3 completes the
dashboard vision for all six product roles — `platform_admin`, `platform_observer`,
`team_admin`, `team_editor`, `team_analyst`, `team_member` — and every new piece of
it is designed as a thin extension of one of those three existing systems (KPI
presets, capability enablement, task bus), never a fourth parallel one. This is a
deliberate constraint, not a stylistic preference: the goal is that this richer
KPI surface adds close to zero new UI-component code and a small, well-placed
amount of backend code.

**Deployment topology note.** Fred has no monolithic agentic backend. The control
plane (`fred-control-plane`) is the central product API. Pod agents are independent
services built on `fred-runtime` (e.g. `fred-agents`); the frontend contacts them
directly using addresses provided by the control plane. The middleware must therefore
be deployed in all user-facing backends independently.

---

## 2. Proposed Solution

### 2.1 — Required Metrics and How to Source Them (v1/v2, implemented, unchanged)

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

### 2.2 — KPI Middleware (v1/v2, implemented, unchanged)

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

### 2.3 — Analytics Query Endpoint (preset-based, v1/v2, implemented; v3 extends scoping)

The preset registry and query endpoint live in `fred-control-plane`. This is
the natural home: it is the central product API, already aware of the full
resource graph (teams, agents, users), and already connected to OpenFGA for
authorization. All backends write KPI events to the same shared OpenSearch
index — the control plane queries that index on behalf of all of them.

`GET /control-plane/v1/kpi-presets/<name>` — each preset is a `PresetDef`
auto-mounted by the registry (`apps/control-plane-backend/control_plane_backend/kpi/`).

**Design principles (unchanged):**

- The backend owns all query logic. The client sends only: preset name + safe
  typed parameters (date range, optional granularity, **v3: optional `team_id`**).
- The authorization scope is injected server-side and cannot be influenced by
  the client.
- The response is shaped data (`[{date, value}]`, `[{label, count}]`) — not
  raw OpenSearch response objects.
- Presets are an explicit allow-list; unknown presets return 400.
- New presets are added by extending the registry — no endpoint changes needed.

**v3 minimality decision — parameterize, don't duplicate.** The ten presets
already shipped for Page 1 (`active_users_over_time`, `sessions_over_time`,
`messages_over_time`, `top_agents_by_conversations`, `documents_total`, etc.)
answer the same questions Page 2 (team dashboard) needs, just at a different
scope. Rather than fork a `team_*` preset per existing preset — doubling the
handler count for no new query logic — **each existing handler that can be
usefully team-scoped gains an optional `team_id` query parameter**, with a
second authorization branch: no `team_id` → `CAN_OBSERVE_PLATFORM` against the
org (unchanged); `team_id` given → `CAN_READ_MEMBERS` against that team (the
same permission `TaskActivity`'s team scope already uses, §2.8 — one
authorization vocabulary for "can this user see this team's operational
data", not two). This is a one-line branch per handler, not a new preset file.
Presets that are genuinely new content (conversation stats, storage,
green/cost — §2.5, §2.7) are added once, already `team_id`-aware from the
start.

### 2.4 — Authorization via ReBAC (OpenFGA)

The endpoint resolves the requesting user's scope from OpenFGA before building
the OpenSearch query. The scope is a mandatory filter injected into the query
— it is not a parameter the client controls.

```
Platform-wide presets, no team_id (Page 1, shared observer+admin):
  Check(user, can_observe_platform, organization) → allow, no team filter

Platform-wide presets, admin-only extension (Page 1, admin section — §2.5):
  Check(user, can_manage_platform, organization) → allow
  (same permission already gating /admin/capabilities and scope=platform task queries —
  no new capability introduced for this RFC)

Team-scoped presets, team_id given (Page 2):
  Check(user, can_read_members, team:<team_id>) → allow, filter WHERE dims.team_id = team_id
  (same permission TaskActivity's scope=team already requires — §2.8)

Personal presets (Page 3):
  inject: WHERE dims.user_id = requesting_user.uid  (no OpenFGA call needed)
```

A user who is not a platform admin/observer receives 403 for platform-wide
presets. A user without `can_read_members` on the requested team receives 403
for that team's presets — this is stricter than `hasElevatedTeamRole()` alone
would imply on the frontend, but `can_read_members` is already satisfied by
every one of `team_admin`/`team_editor`/`team_analyst` (§8.1,
`AGENT-CAPABILITY-RFC.md`), so no elevated-role holder is ever blocked; a
plain `team_member` is — consistent with §2.5's decision that the team
dashboard is not part of the plain-member experience.

### 2.5 — Frontend Dashboards: the six roles

**Role model** (`docs/swift/platform/REBAC.md`, `schema.fga` — exact names,
no platform-level `analyst`/`editor`/`member`):

| Scope | Roles |
|---|---|
| Platform (`organization:fred`) | `platform_admin`, `platform_observer` (`platform_admin` always satisfies `platform_observer` too) |
| Team (`team:<id>`, per-team, a user may hold several) | `team_admin`, `team_editor`, `team_analyst` — orthogonal, not hierarchical; `team_member` is the baseline every elevated role implies |

Three pages, as v1/v2 planned, but Page 2 is now fully specified and Page 3 is
unchanged:

#### Page 1 — Platform dashboard (`/admin/analytics`, existing `AnalyticsPage`)

Shared section — **`platform_observer` and `platform_admin` both see this**,
gated on `can_observe_platform` (unchanged from v1/v2):

- The 10 shipped presets: `active_users_over_time`, `unique_users_total`,
  `sessions_over_time`, `messages_over_time`, `sessions_by_scope`,
  `top_teams_by_sessions`, `agents_total`, `agent_prompt_length_distribution`,
  `top_agents_by_conversations`, `documents_total`.
- **New (v3):** token consumption over time, by agent, by model — reusing the
  same `*Detail`/dims `agent.turn_completed` already emits (the exact data
  the personal dashboard already charts, §2.1/Page 3 — aggregated
  platform-wide instead of per-user). New preset: `token_usage_over_time`
  (+ `_by_agent`, `_by_model`), no new instrumentation.
- **New (v3):** the same token-usage charts also render the green/cost
  equivalents defined in §2.7, inline — not a separate panel.
- Issue #1777 (closed, UX critique: "too much scrolling, too dense") should be
  addressed in the same pass this section adds new stat tiles — group into
  collapsible sections (`Disclosure` atom, already used elsewhere in the
  design system) rather than growing one flat scroll.

Admin-only section — **`platform_admin` only**, gated on `can_manage_platform`
(new gate for these specific widgets; §2.4):

- **Storage by team** (new preset `storage_by_team`, reads
  `TeamMetadataStore.list_all()` directly — `current_resources_storage_size`
  against the already-resolved `max_resources_storage_size`, §2.9) — a
  `BarChart` (reused molecule) with the quota line overlaid, so "which teams
  are near their quota" is a glance, not a computation the admin does by
  hand.
- **Activités** (platform-wide task/problem load) — §2.8: not a chart, an
  embed of the existing `TaskActivity` organism at `scope="platform"`.
  Already reachable today at `/admin/tasks`; this RFC's only frontend change
  here is surfacing it as a section/link from the Analytics page rather than
  requiring the admin to already know that route exists.
- **Models governance** — link to `/admin/capabilities?kind=model`
  (`AGENT-CAPABILITY-RFC.md` §8.7). No new UI in this RFC; this page cross-links
  to it.

#### Page 2 — Team dashboard (new: one page, capability-conditional sections)

**Placement decision.** `apps/frontend/src/rework/components/pages/TeamUsagePage`
already exists at `/team/:teamId/usage` and already renders exactly the
`team_member` baseline content (§ below) under the description "no team/agent
picker: this is 'my own consumption'". Rather than a new route/page, **this
page is extended in place**: the personal-consumption section stays exactly as
built (every team member, including plain `team_member`, keeps seeing it,
unchanged), and new sections are prepended above it, each gated by
`useTeamCapabilities()`/`hasElevatedTeamRole()` (both already exist,
`teamCapabilities.ts`) — no new route guard component, following the
documented in-page-gating pattern (`FRONTEND-AUTHZ-PATTERN.md`: "every
`/team/:teamId/...` route renders unconditionally, team-level gating happens
inside the page"). This keeps the "one page, conditional sections" model
consistent with how the rest of the team surface already works, and adds a
route-level change of exactly zero.

**`team_member` (baseline, unchanged, already built):**

- Their own token usage over time / by agent / by model — the existing
  personal-consumption section, verbatim.
- **New (v3):** the same green/cost equivalents as everywhere else (§2.7).

**Shared section — anyone with an elevated role sees this** (`team_admin` OR
`team_editor` OR `team_analyst`, i.e. anyone who can reach this section at
all — same content as `platform_admin`'s base, team-scoped):

- Team usage: members, agents, most-active-agents, documents — the
  `team_id`-parameterized presets from §2.3.
- Token consumption (team-scoped `token_usage_*` presets) + green/cost
  equivalents.
- Team quota status: `storage_by_team` filtered to this one team (§2.9) — the
  same widget as platform_admin's, one team's row instead of the full ranked
  table.
- Conversation statistics: count over time (reuses `sessions_over_time`,
  `team_id`-scoped — no new preset). **Open item, not yet decided:** the
  breakdown/distribution dimension ("une manière à déterminer de voir la
  répartition") — `top_agents_by_conversations` (already `team_id`-scoped per
  §2.3) is the natural default (breakdown by agent); confirm at Step 3 or
  leave as a fast-follow once the count-only view is live and it's clearer
  what breakdown is actually useful.

**`team_editor` additional section** (focus: corpus maintenance):

- Activités, team-scoped, `kind="ingestion"` — `<TaskActivity scope="team"
  teamId={id} kind="ingestion" />`. No new preset, no new component.

**`team_analyst`:** no dashboard-specific content beyond the shared section
above. Evaluation work (launching runs, and — planned, not yet built —
reading team conversations to build evaluations) lives in the existing
Evaluation tab, not on this dashboard. Out of scope for this RFC.

**`team_admin` additional section** (focus: governance):

- Activités, team-scoped, unfiltered by kind — `<TaskActivity scope="team"
  teamId={id} />` (broader than `team_editor`'s ingestion-only filter — same
  component, different `kind` prop).
- Team activity/inactivity summary — **new preset**, `team_activity_summary`:
  last-active timestamp + a simple trend flag, derived from `sessions_over_time`
  for that team (no new instrumentation, just a different shape of an existing
  aggregation).

#### Page 3 — Personal dashboard (`/team/:teamId/usage`, `team_member` baseline above — unchanged)

No change beyond the green/cost addition already listed under `team_member`
above. This is the same component and the same data source platform-wide
token usage (Page 1) and team-scoped token usage (Page 2) already reuse — one
"token usage" concept, rendered at three scopes by three different preset
parameterizations of the same query shape.

### 2.6 — Caching strategy (v1/v2, implemented, unchanged)

With multiple replicas and no shared cache, per-replica in-process caches
produce inconsistent results across page refreshes. The chosen strategy
avoids this:

- **No server-side cache.** Analytics queries are served directly from
  OpenSearch on every request.
- **OpenSearch as the cache.** OpenSearch keeps hot query results in its
  request cache (enabled by default for aggregations on static time ranges).
- **Client-side TTL.** The frontend caches the response for a configurable
  TTL (e.g. 5 minutes) and does not re-fetch on every render.
- **Date range design.** Preset parameters use closed time ranges (`from`/`to`).
  "Today so far" queries are inherently live and do not benefit from caching
  — this is acceptable and expected behavior.

This approach gives consistent results across replicas with zero infrastructure
additions.

### 2.7 — Green metrics and optional cost estimation (v3, new)

**Why essential, not optional.** Carbon (CO₂e) and electricity-consumption
equivalents are shown **everywhere token usage is shown** — Page 1 platform-wide,
Page 2 team-scoped, Page 3 personal — as a first-class part of the token-usage
widgets, not a separate panel. Cost in $ is the opposite: useful, but
secondary, and rendered as an optional/collapsible add-on next to the same
widgets.

**One static config, two independent columns.** A single new config file
(location: alongside other static Fred config, e.g.
`libs/fred-core/fred_core/kpi/model_impact_factors.yaml` — final path
confirmed at Step 4) keyed by `model_name`, the same key `agent.turn_completed`
already emits:

```yaml
models:
  gpt-5.1:
    cost_per_1k_input_tokens: 0.0        # $, optional column — populate or leave 0
    cost_per_1k_output_tokens: 0.0
    co2e_grams_per_1k_tokens: 0.0        # required column
    kwh_per_1k_tokens: 0.0               # required column
  default:                                # fallback row for any model_name not listed
    co2e_grams_per_1k_tokens: 0.0
    kwh_per_1k_tokens: 0.0
```

Both are estimates from a hand-maintained table, not billing-grade or
measurement-grade — the UI must label them "estimated," matching how §2.1
already treats resource gauges as approximations sourced from a different
system than the one that will eventually be authoritative.

**No new endpoint.** The three token-usage presets (§2.5, at every scope)
compute both columns server-side alongside the raw token count, from the same
`agent.turn_completed` aggregation — one query, three numbers per point
(tokens, CO₂e, kWh, + optional $), not three separate preset calls. Config is
static (file, dev-edited) for v1 — no admin UI to edit it (§2.9 found this
RFC needs no new admin settings surface at all).

### 2.8 — Activités: reusing the task bus, not building a fourth system (v3, new)

**No new component.** Every "Activités" panel in §2.5 (platform-wide,
team-scoped, ingestion-filtered) is the existing `TaskActivity` organism
(`apps/frontend/src/rework/components/shared/organisms/TaskActivity/TaskActivity.tsx`)
— already built exactly to spec (`TASK-EVENT-STREAM-RFC.md` §3.4), already
reused at both `scope="platform"` and `scope="team"`, driven entirely by
props (`scope`, `teamId`, `kind`). This RFC adds zero new task-list UI.

**One real gap, fixed in its proper home.** The one piece these dashboards
need that didn't already exist — a server-persisted "an admin has seen and
handled this" acknowledgement, visible to every other admin of that scope,
not a per-browser flag — is a task-bus concern, not a KPI-analytics concern.
It is specified and amended into `TASK-EVENT-STREAM-RFC.md` §2.10 (rev. 3),
not here: new `acknowledged_at`/`acknowledged_by` columns on `task_run`, a
`POST /tasks/{id}/ack` endpoint reusing the existing task-read authorization,
and `TaskDetailPopover`/`TaskCard` wired to call it. This RFC's dashboards are
simply a consumer of that fixed, shared mechanism.

**Known, pre-existing, out-of-scope divergence.** `TASK-EVENT-STREAM-RFC.md`
§3.4 specifies Activity as a first-class nav item, a peer of Members/Settings.
Today the team-scoped view is nested inside Team Settings
(`/team/:teamId/settings/activity`) and the platform view is at `/admin/tasks`,
not `/admin/activity`. This RFC does not restructure that navigation — it is
a pre-existing gap in OPS-04's own implementation, unrelated to the dashboard
content this RFC adds, and changing nav structure is out of scope here to
avoid bundling an unrelated UX change into this delivery. Flagged for a
separate, small follow-up if wanted.

### 2.9 — Storage quota and retention: already built, not new (v3 correction)

**Correction (2026-07-25, mid-implementation).** This section originally
proposed a new "platform settings" surface for a global storage quota and a
global retention duration, on the premise that neither existed. Both
premises were wrong — found while implementing §2.5's quota-status panels,
before any of this section's originally-proposed code was written:

- **Retention is already fully built, per-team, admin-editable.**
  `TeamMetadata.team_delete_grace` / `max_idle` (CTRLP-12) are real,
  patchable fields (`TeamMetadataPatch`, `libs/fred-core/fred_core/teams/metadata_store.py`)
  with a full resolution pipeline already in production
  (`scheduler/policies/retention_resolver.py`, `policy_engine.py`). There is
  nothing to build — this RFC needed nothing here and adds nothing here.
- **Storage quota partially exists.** `TeamMetadata.max_resources_storage_size`
  (alongside `current_resources_storage_size`) is a real field, already read
  everywhere that matters — enforced in the upload flow
  (`DocumentUploadDrawer.tsx`), exported/imported by the migration bundle. It
  resolves to a platform-wide config default
  (`config.app.default_team_max_resources_storage_size`) when a team has no
  override (`teams/service.py:1204-1206`). The one real, narrow gap: `max_resources_storage_size`
  is **not** in `TeamMetadataPatch` — there is no way to set a per-team
  override today, only the static config default. That gap is small
  (`TeamMetadataPatch` already carries the identical pattern for
  `team_delete_grace`; adding `max_resources_storage_size` is the same shape
  of change) and is **not required** for §2.5's dashboards — a quota-status
  panel reads `current_resources_storage_size` against whatever
  `max_resources_storage_size` already resolves to (override or platform
  default), whether or not an admin can change that override from the UI yet.

**Revised scope: none.** §2.5's storage/quota panels (`storage_by_team`
preset) read `TeamMetadataStore.list_all()`/`get_by_id()` directly — no new
settings table, no new endpoint, no new admin page. The
`max_resources_storage_size`-in-`TeamMetadataPatch` gap is noted as a
possible tiny follow-up (not this RFC's scope, not blocking anything here),
should an admin ever want to override the platform default per team from the
UI rather than editing deploy config.

**Do not confuse with FILES-05.** The filesystem-hardening track (workspace
scratch-space quotas, `WorkspaceCapability`) is a *different* storage pool
from the document/resource library `max_resources_storage_size` covers here
— FILES-05's quota work remains genuinely unbuilt and unrelated to this
correction.

---

## 3. Alternatives Considered

**Pass raw OpenSearch queries from the frontend.**
Rejected. Exposes storage internals, cannot enforce authorization scope, and
allows clients to run arbitrary expensive aggregations.

**Redis for shared cache.**
Rejected for this RFC. Adds an infrastructure dependency. OpenSearch's own
request cache is sufficient for the defined use cases.

**Preset registry in `fred-core` shared across all backends.**
Rejected. Distributing query endpoints across backends would duplicate
authorization logic and split the API surface.

**Keycloak event log for login counts.**
Rejected as primary source. The backend never observes login events — only
subsequent API calls.

**(v3) A `team_*` preset fork per existing platform preset.**
Rejected. Ten new handler files duplicating ten existing ones for the same
query shape at a different scope, doubling maintenance for zero new query
logic. An optional `team_id` parameter with a second authorization branch
(§2.3) delivers the same capability from the same code.

**(v3) A new generic "Notification"/"Alert" domain model for Activités.**
Rejected. No such model exists in Fred today, and building one would
duplicate the task bus's `TaskState`/`TaskTarget`/scope/authorization model
almost exactly. Every acknowledgeable item this RFC's dashboards surface
(ingestion failures, stalled erasure) is already a task; extending the task
bus with persisted acknowledgement (§2.8, `TASK-EVENT-STREAM-RFC.md` §2.10)
is strictly less code than a parallel notification system, and gives every
future task kind acknowledgement for free.

**(v3, superseded) Per-team storage quota override in v1.**
Originally rejected on the premise that no quota field existed yet.
Superseded (§2.9 correction): the field (`max_resources_storage_size`) and
its config-default resolution already exist and ship today — there was
never a decision to make here. The only real remaining question — should
`max_resources_storage_size` join `TeamMetadataPatch` so an admin can set a
per-team override from the UI — is a small, separate, non-blocking follow-up,
not a v1/v1.1 scope call for this RFC.

**(v3) Building a dedicated per-model pricing/carbon table editable via UI.**
Rejected for v1. Static, dev-edited config is enough; both tables are
estimates already, and an editable UI is meaningful added scope (new
endpoint, new admin page, validation) for a number that changes rarely.

---

## 4. Impact on Existing Contracts

| Contract | Change |
|----------|--------|
| `RUNTIME-EXECUTION-CONTRACT.md` | No change — middleware is transport-level; §8.7's model-enforcement gap (`AGENT-CAPABILITY-RFC.md`) is a `fred-runtime` follow-up, not a contract change in this RFC |
| `CONTROL-PLANE-PRODUCT-CONTRACT.md` | New: `team_id`-parameterized existing presets (§2.3); new presets (`token_usage_*`, `storage_by_team`, `team_activity_summary`). No new settings endpoint (§2.9 correction — nothing to add there). To be added at Step 4. |
| `TASK-EVENT-STREAM-RFC.md` (OPS-04) | Amended directly (rev. 3, §2.10) — new `POST /tasks/{id}/ack`, new `task_run` columns. Not duplicated here. |
| `AGENT-CAPABILITY-RFC.md` | Amended directly (§8.7) — `kind="model"`. Not duplicated here. |
| `PrometheusKPIStore` | No change |
| `KPIWriter` | No change |

---

## 5. Development Plan

Phased as one v1 delivery — no item below is deferred to a "v1.1" milestone;
the only intentional scope cuts already made are listed in §3 (editable
pricing/carbon UI) and are not tracked as follow-up work here, only as
documented non-goals. §2.9's original B8/F6 (platform settings page) were
removed mid-implementation once found redundant with already-shipped
per-team quota/retention fields (§2.9 correction) — no replacement item
added, there is nothing to build there.

### 5.1 Backend

| # | Task | Touches | Depends on |
|---|---|---|---|
| B1 | `team_id`-parameterize the existing 10 platform presets (§2.3) | `control_plane_backend/kpi/presets/*.py` | — |
| B2 | New presets: `token_usage_over_time`/`_by_agent`/`_by_model` (platform + team scope), `storage_by_team` (reads `TeamMetadataStore` directly, §2.9), `team_activity_summary` | `control_plane_backend/kpi/presets/` | B1 (auth pattern) |
| B3 | Green/cost computation layer + `model_impact_factors.yaml` loader | `fred-core` (new small module) | — |
| B4 | Wire B3 into the token-usage presets from B2 | `kpi/presets/token_usage_*.py` | B2, B3 |
| B5 | `task_run.acknowledged_at`/`acknowledged_by` columns + `POST /tasks/{id}/ack` | `fred-core/tasks/`, both backend routers | `TASK-EVENT-STREAM-RFC.md` §2.10 sign-off |
| B6 | `kind="model"` capability projection + `KIND_FILTERS` backend enum widen | `capabilities/catalog.py`, `fred-sdk` manifest | `AGENT-CAPABILITY-RFC.md` §8.7 sign-off |
| B7 | Model-routing enforcement chokepoint (fail-closed on disabled model) | `fred-runtime/model_routing/` | B6 — flagged in §8.7 as needing its own design confirmation before implementation |
| B9 | Regenerate OpenAPI + RTK Query client for every backend touched (B1–B2, B5, B6) | `make update-control-plane-api`, `make update-runtime-api` | B1–B7 |

### 5.2 Frontend

| # | Task | Touches | Depends on |
|---|---|---|---|
| F1 | `AnalyticsPage`: token-usage + green/cost widgets, admin-only section (storage/quota, Activités link, capabilities link), collapsible grouping (#1777) | `AnalyticsPage.tsx` | B2, B4, B9 |
| F2 | `TeamUsagePage`: prepend capability-conditional sections (shared usage/quota/conversations, editor Activités, admin Activités+summary) above the unchanged personal section | `TeamUsagePage.tsx` | B2, B4, B9 |
| F3 | Embed `<TaskActivity>` in F1/F2 (no component change) | — | existing component |
| F4 | `TaskDetailPopover`/`TaskCard`: wire the ack action, remove `failuresAcknowledged` client-only path | `molecules/TaskDetailPopover`, `TaskCard`, `taskSlice.ts` | B5, B9 |
| F5 | `CapabilitiesPage`: widen `KIND_FILTERS` to include `"model"` + i18n key | `CapabilitiesPage.tsx` | B6, B9 |

### 5.3 Sequencing

Backend-first within each vertical slice (a preset/endpoint must exist before
its frontend consumer is wired), but the three verticals — dashboards (B1-4,
F1-3), acknowledgement (B5, F4), models-as-capability (B6-7, F5) — are
independent of each other and can proceed in parallel. B7 (runtime
enforcement) is the one item on the critical path that needs an explicit
design confirmation before any code is written (§8.7) — start it early given
that lead time, even though its frontend consumer (F5) doesn't block on it.

### 5.4 Tests

Per `docs/CONVENTIONS.md` — unit tests for every new preset's authorization
branch (org-scope vs. team-scope vs. rejected), the green/cost computation
(known input → known output against the static config), the ack endpoint's
409-when-not-needed-attention and 200-when-needed-attention paths, and the
`kind="model"` catalog projection (profile → deduplicated model entries).
Frontend: component tests for the new `TeamUsagePage` sections' conditional
rendering per capability, and for the ack affordance's visibility predicate.
No live-stack integration tests — per standing convention, reason statically
and let the developer run live verification.

---

## 6. Open items requiring explicit Step 3 sign-off

Carried over from inline notes above, collected here so none is missed. Both
resolved during implementation (2026-07-26), neither redirected:

1. **§2.5** — the team-dashboard conversation "répartition" breakdown
   dimension (defaulting to by-agent unless redirected). Resolved: shipped
   with the default — F2's shared section's `MultiSeriesLineChart` reuses
   `top_agents_by_conversations`, team-scoped, as both "most active agents"
   and the conversation breakdown.
2. **§8.7 (`AGENT-CAPABILITY-RFC.md`)** — the model-routing fail-closed
   fallback behavior when a resolved profile's model capability is disabled.
   Resolved: implemented as B7 (explicit error, never silent substitution).

(§2.9's original item — confirm the single-global-quota scope cut — is
withdrawn: the premise it was asking about turned out to be false, see the
§2.9 correction above.)
