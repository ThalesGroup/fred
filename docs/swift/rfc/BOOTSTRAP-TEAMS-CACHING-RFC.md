# RFC — Bootstrap/Teams Latency: Bounded Read-Side Caching + Frontend Refetch Fix

## Status

implemented (2026-07-29) — backend caches (§2.1/§2.2), invalidation-on-write,
frontend refetch-policy fix (§2.3), and tests (§6.3) are done and passing
(`make code-quality`/`make test` green in both `apps/control-plane-backend`
and `apps/frontend`; `fred-performance-reviewer` run, no blocking findings).
Benchmark (§2.4) not yet run — pending a live/manual pass before commit per
standing project convention (no commit on UI-facing frontend work before a
manual browser check).

## Authors

Dimitri Tombroff

## Task ID

Continuation of `AUTHZ-2065` (#2065, PR #2145). Tracked by issue #2148.

## Version

v1

---

## 1. Context and Motivation

`GET /control-plane/v1/frontend/bootstrap`, `GET /teams`, and `GET /teams/all`
share one enrichment path (`_list_teams` →
`_enrich_teams_with_membership`, `control_plane_backend/teams/service.py:332-401`)
that is still measured at 4-8s in the S3NS environment (~99 teams), despite
`AUTHZ-2065` (#2065/#2145) already replacing a `2×N` `ListUsers` fan-out with
a cheaper `1×N` `Read` fan-out. Two independent linear fan-outs remain, plus
an unrelated frontend issue that multiplies how often they're paid for. Full
investigation is in issue #2148; this RFC proposes the fix.

**Problem 1 — OpenFGA team-membership fan-out.** `_bulk_team_membership`
(`teams/service.py:1217-1266`) issues one `list_direct_relations(team:<id>)`
call per team, concurrently, every time the list is built. A constant-size
bulk alternative was investigated as part of #2148 and is **not viable**:
OpenFGA's `Read` requires either an exact object id or an exact subject to
anchor the query; `list_relations` filtered by object-type-only + a named
relation (the shape issue #2091 separately assumed workable for `capability`
tuples) still requires a non-optional `subject`
(`libs/fred-core/fred_core/security/rebac/openfga_engine.py:304-325`,
`rebac_engine.py:791-798`) and hits the same documented HTTP 400 as the
earlier attempt when that subject is omitted
(`teams/service.py:1217-1234`, `test_teams_bulk_membership_call_count.py:19-28`).
This has been flagged on #2091 as well. The per-team `Read` fan-out is
therefore the minimal call shape achievable against OpenFGA's actual Read
semantics — the lever left is reducing how often it runs, not its shape.

**Problem 2 — Keycloak admin-lookup fan-out.** `get_users_by_ids`
(`control_plane_backend/users/service.py:217-266`) fires one Keycloak Admin
REST `a_get_user(id)` call per distinct team-admin id, concurrently, to
resolve display names. This was out of scope for `AUTHZ-2065` (OpenFGA-only)
and has no cache today.

**Correction (2026-07-29):** an earlier pass of this investigation
incorrectly stated no caching primitive exists in this codebase. It does:
`fred_core.common.ThreadSafeLRUCache`
(`libs/fred-core/fred_core/common/lru_cache.py`) is already used twice with
an established TTL-on-top-of-LRU convention — callers store
`(expires_at, value)` tuples and check freshness at the call site, deleting
on staleness. See `_JWT_CACHE` (`libs/fred-core/fred_core/security/oidc.py:69`,
`JWT_CACHE_TTL_SECONDS`/`_load_cached_user`) and `_WHITELIST_CACHE`
(`libs/fred-core/fred_core/security/whitelist_access_control/access_control.py:27`).
This RFC's caches follow the exact same convention rather than introducing a
new cache abstraction or dependency — see §2.1/§2.2.

**Problem 3 — frontend forced refetch.** `useFrontendBootstrap.ts:36-42` and
every KPI-preset query in `AnalyticsPage.tsx`/`TeamUsagePage.tsx` set
`refetchOnMountOrArgChange: true`, forcing a full network round-trip on every
page mount regardless of cache freshness — contradicting
`KPI-ANALYTICS-RFC.md` §2.6 ("does not re-fetch on every render"). This
multiplies how often Problems 1 and 2 are paid for during ordinary
navigation.

---

## 2. Proposed Solution

### 2.1 Bounded, per-replica, in-memory TTL cache for team-membership reads

Reuse `fred_core.common.ThreadSafeLRUCache` with the same
`(expires_at, value)` convention as `_JWT_CACHE`/`_WHITELIST_CACHE` — no new
dependency, no new abstraction. A module-level
`ThreadSafeLRUCache[TeamId, tuple[float, RelationsResult]]` in
`teams/service.py`, keyed by `team_id`:

- TTL: 45s (bounds display staleness to well under one user-perceived
  "still feels live" window; flagged as an open item below in case 45s is
  judged too long for a given team-membership-change workflow).
- `get` → if present and `expires_at > now`, return cached value; else
  `delete` and fall through to a live `list_direct_relations` call, then
  `set` the fresh result with a new `expires_at`. Identical control flow to
  `_load_cached_user`/`_cache_user` in `oidc.py`.
- Scope: **per replica, in-process.** No Redis, no new shared infrastructure.
  Each replica's cache warms independently; worst case under a fresh
  deployment or replica restart is one full-cost fan-out per replica, not a
  correctness issue.
- **No single-flight/stampede lock**, matching the simplicity of the two
  existing `ThreadSafeLRUCache` call sites (neither has one). A stampede here
  means at most a handful of redundant concurrent `list_direct_relations`
  calls for the same team while its entry is cold — bounded, not
  cascading, and not worth the added complexity unless benchmarking (§2.4)
  shows real contention.

### 2.2 Short-TTL cache for Keycloak admin display names

Same pattern, same primitive, second module-level
`ThreadSafeLRUCache[str, tuple[float, UserSummary]]` in `users/service.py`,
keyed by `user_id`, TTL 5 minutes — display names change far less often than
team membership, and a stale name for up to 5 minutes has no functional
consequence beyond a cosmetic delay in reflecting a rename.

### 2.3 Frontend: stop forcing a refetch on every mount

- **Bootstrap.** Remove `refetchOnMountOrArgChange: true` from
  `useFrontendBootstrap.ts` entirely — the bootstrap query had no
  `providesTags` at all (verified: not present in
  `controlPlaneApiEnhancements.ts`), so it relied solely on the forced
  refetch to stay fresh. Fix that properly: add `providesTags` mirroring
  `listTeams`'s pattern (one tag per team id in `available_teams`, plus
  `active_team.id`, plus the shared `LIST` tag) so every existing
  team-mutating endpoint (`joinTeam`, `addTeamMember`, `grantTeamMemberRole`,
  etc. — all already invalidate `ControlPlaneTeam` tags) invalidates
  bootstrap's cache entry too. No numeric TTL needed here — mutation-driven
  invalidation is precise; RTK Query's default `keepUnusedDataFor` bounds
  staleness from changes made outside this app.
- **KPI presets (`AnalyticsPage.tsx`/`TeamUsagePage.tsx`).** These have no
  mutations to invalidate them (pure reporting reads), so bare removal would
  under-refresh (serve indefinitely stale data once cached). Set
  `refetchOnMountOrArgChange: 300` (RTK Query's numeric form: refetch on
  mount only if the cached entry is older than 300s) instead of `true` —
  this is the literal "5 minute client-side TTL... does not re-fetch on
  every render" `KPI-ANALYTICS-RFC.md` §2.6 already documents but the
  shipped code never implemented (it used the boolean `true` form, which
  ignores age entirely and always refetches).

### 2.4 Benchmark

Land the p50/p95/p99 measurement for `/frontend/bootstrap`, `/teams`,
`/teams/{id}` that PR #2145 promised as a follow-up, before/after this
change, at a team/membership cardinality representative of S3NS (~99 teams),
not just the 3/50-team unit-test fixtures.

---

## 3. Alternatives Considered

- **Bulk OpenFGA Read (type + relation, no subject).** Investigated and
  ruled out — see Problem 1. Would have been strictly better than caching
  (no staleness, no new infrastructure) had it worked.
- **Postgres read-model/projection for team membership**, kept in sync via
  write-through on every membership-mutating call. Would fully eliminate the
  OpenFGA read fan-out (O(1) SQL query instead of O(N) `Read` calls) but
  requires touching every membership write path (join, invite-accept, role
  change, leave) to keep the projection correct, and introduces a second
  source of truth for data OpenFGA already owns. Out of scope for this RFC;
  worth reopening only if the TTL-cache approach proves insufficient at
  larger scale (e.g. 500+ teams) after this lands and is measured.
- **Frontend-only fix (Problem 3 alone).** Reduces call *frequency* but
  leaves the *per-call* cost at 4-8s for the first navigation and for any
  concurrent user — insufficient alone.
- **Backend-only fix (Problems 1-2 alone).** Reduces cost per call but still
  pays it on every page navigation for every user — the frontend fix
  compounds with the backend fix rather than substituting for it.

---

## 4. Reconciliation with `KPI-ANALYTICS-RFC.md` §2.6 ("No server-side cache")

That decision explicitly concerns **computed analytics aggregates**: "with
multiple replicas and no shared cache, per-replica in-process caches produce
inconsistent results across page refreshes" — i.e., two users hitting two
different replicas could see two different *numbers* for the same KPI query,
which is a correctness problem for a reporting surface.

This proposal caches **raw entity reads** (a team's membership tuples, a
user's display name), not derived/aggregated values, and only for
list/display purposes:

- No authorization decision is ever served from this cache — `Check` calls
  (`CAN_READ`, `CAN_MANAGE_PLATFORM`, etc.) remain live and uncached, exactly
  as today.
- The "inconsistency across replicas" concern from §2.6 degrades here to "a
  team's displayed member count may lag by up to 45s depending which replica
  served the request" — a bounded, cosmetic staleness window, not an
  incorrect aggregate computation.
- Given this is a materially different class of caching than what §2.6
  rejected, this RFC does not amend §2.6 — it documents why this case falls
  outside that decision's scope rather than contradicting it.

---

## 5. Impact on Existing Contracts

None. Response shapes for `/frontend/bootstrap`, `/teams`, `/teams/all` are
unchanged — this is an internal implementation detail behind the existing
`Team`/`TeamSummary` schemas. No OpenAPI regeneration required.

---

## 6. Development Plan

### 6.1 Backend

- Reuse `fred_core.common.ThreadSafeLRUCache` (already a `fred-core` public
  export, already imported by two other call sites) — no new dependency.
- Wrap `_bulk_team_membership`'s per-team `list_direct_relations` call (45s
  TTL) and `get_users_by_ids`'s per-user Keycloak call (5min TTL), following
  the exact `(expires_at, value)` get/delete/set convention already used by
  `_JWT_CACHE`/`_WHITELIST_CACHE`.
- No change to `_list_teams`, `_enrich_teams_with_membership`, or response
  schemas — the cache sits strictly inside the existing per-team/per-user
  call sites.

### 6.2 Frontend

- Remove `refetchOnMountOrArgChange: true` from `useFrontendBootstrap.ts`
  and from each KPI-preset hook call in `AnalyticsPage.tsx`/`TeamUsagePage.tsx`.
- Audit `invalidatesTags`/`providesTags` wiring for team-membership and
  KPI-affecting mutations; add any missing invalidation so removing forced
  refetch doesn't regress freshness after a user action.

### 6.3 Tests

- Extend `test_teams_bulk_membership_call_count.py` with cache hit/miss/TTL
  -expiry cases, parametrized at a realistic scale (100+ teams).
- New call-count regression test for `get_users_by_ids` (cold miss / warm
  hit / TTL-expired).
- Concurrency test: N simultaneous callers for the same expired key trigger
  exactly one upstream fetch (single-flight correctness).
- Frontend: verify (manual or automated) that a team-membership-changing
  mutation is reflected without needing the old forced refetch.
- `fred-performance-reviewer` skill run before close — this touches a shared
  client/cache on a per-request call site under concurrent load.
- `make code-quality` and `make test` green in `apps/control-plane-backend`
  and `apps/frontend`.

### 6.4 Sequencing

1. Backend caches (2.1, 2.2) + tests — independently shippable, immediate
   latency win regardless of frontend state.
2. Frontend refetch-policy fix (2.3) + tag-invalidation audit.
3. Benchmark (2.4) to confirm the measured improvement and decide whether
   further work (e.g. the Postgres projection alternative) is warranted.

---

## 7. Sign-off (resolved 2026-07-29)

- **TTL values.** 45s (membership) / 5min (Keycloak names) — confirmed as-is.
- **Cache primitive.** Reuse `fred_core.common.ThreadSafeLRUCache` (existing,
  no new dependency) — confirmed after catching that an earlier pass of this
  investigation had incorrectly claimed no caching primitive existed in the
  codebase; see the Problem 2 correction note above.
