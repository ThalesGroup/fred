# OBSERV-02 v3 — follow-up notes (not this branch's scope)

Working notes kept alongside issue #2110 while implementing the OBSERV-02 v3
KPI dashboard work (`CONTROL-PLANE-PRODUCT-CONTRACT.md` §36). Each entry below
is something found *while building*, deliberately left out
of this branch, and worth its own small GitHub issue later. Not a design doc —
just enough context per entry to write that issue without re-deriving it.

---

## Backend — KPI presets

### 1. ✅ RESOLVED 2026-07-29 — `documents_total` now team-scoped
`document.created_total`/`document.deleted_total` KPI events DO carry
`dims.team_id` (knowledge-flow resolves it from the document's first tag
owner — `features/metadata/service.py:824`), but `PostgresDocumentMetadataStore`
had no team-scoped count, and a document's team is indirect (via tag
ownership, not a column). Fixed by adding
`PostgresDocumentMetadataStore.count_by_team(team_id)` (fred-core):
resolves the team's tag ids from `TagRow.owner_id`, then counts documents
whose `tag_ids` overlap that set (Postgres array `&&`, GIN-indexed; Python
fallback for SQLite tests). `DOCUMENTS_TOTAL_PRESET.team_scopable` is now
`True`. No frontend change needed — `TeamUsagePage.tsx` was already sending
`team_id` and hitting the router's 400.

### 2. `agent_prompt_length_distribution` — data available, not wired
`agent.created_total` carries `dims.team_id` (same as `agents_total`), so this
*could* be team-scoped the same way — but the preset runs 3 separate queries
(created/deleted/alive-with-prompt-length) and deserves a careful pass rather
than a rushed one. Deferred, `team_scopable=False`, comment in the file.

### 3. `active_users_over_time` / `unique_users_total` — architecturally blocked
Sourced from `api.request_latency_ms` (the generic HTTP middleware KPI),
which deliberately never carries `dims.team_id` (`CONTROL-PLANE-PRODUCT-CONTRACT.md` §36
— team context can't safely come from request-body reads in middleware,
breaks streaming). Team-scoping these for real would need a *new*,
domain-level KPI event with proper team attribution — not a parameter
threading exercise. Not attempted.

### 4. `token_usage_by_agent` — platform-scale query cost (flagged in code)
OpenSearch can't order a terms aggregation by the sum of two sibling metrics
(input+output tokens) without a `bucket_script`, which it also refuses to
sort by. The accepted workaround (fetch up to 10 000 buckets unbounded, rank
in Python) is fine for one user's handful of agents (existing
`user_token_usage_by_agent.py`) — at PLATFORM scope, with many fred-agents
replicas and potentially thousands of agent instances, this becomes a real
per-request cost on every dashboard load. Two possible fixes for later: (a)
emit a combined `quantities.total_tokens` field at write time
(`agent_app.py`) so OpenSearch can order server-side and the terms agg can be
bounded to `size=TOP_N`; (b) cache this preset's result more aggressively
than the generic client-side TTL (§2.6). Comment left in
`kpi/presets/token_usage_by_agent.py`.

### 5. `max_resources_storage_size` is not admin-editable per team
Confirmed while correcting RFC §2.9: the field exists, is enforced
(`DocumentUploadDrawer.tsx`), resolves to a platform config default when
unset — but `TeamMetadataPatch` doesn't include it, so there is no way to set
a per-team override from the UI today, only via the static
`default_team_max_resources_storage_size` config value (redeploy required to
change it). `team_delete_grace`/`max_idle` already have this exact
UI-editable pattern (CTRLP-12) — adding `max_resources_storage_size` to the
patch schema would be the same shape of change. Not needed for OBSERV-02's
dashboards (they just read whatever it currently resolves to); worth its own
tiny issue if an admin ever asks for it.

---

## Frontend / nav

### 6. Activity page nav placement still diverges from OPS-04 §3.4
`TASK-EVENT-STREAM-RFC.md` §3.4 specifies Activity as a first-class nav item,
a peer of Members/Settings, at `/admin/activity` and `/teams/{id}/activity`.
Shipped reality: `/admin/tasks` (not `/admin/activity`) and the team view
nested inside Team Settings (`/team/:teamId/settings/activity`), not a
sibling nav item. Pre-existing gap, unrelated to OBSERV-02's dashboard
content — noted as explicitly out of scope for
this branch. Small, self-contained follow-up if the nav restructure is
wanted.

### 7. `TaskTray` (sidebar, scope=user) is fully built but not mounted
Found during the initial research pass (not re-verified since): `TaskTray`/
`TaskTrayTrigger` exist, are tested, and are wired into the Redux task slice
— but nothing in `Sidebar.tsx` renders them. A code comment in
`RunCreate.tsx:170` already tracks this ("see BACKLOG.md P4"), so this may
already be a known, intentionally-deferred item — flagging here only in case
it isn't tracked anywhere OBSERV-02-adjacent.

---

## Cross-backend

### 8. No single "all tasks, platform-wide" query exists
Each backend (control-plane, knowledge-flow, the standalone evaluator) keeps
its own `task_run`/`task_event_log` tables (or, for the evaluator, no
`task_run` at all — a live projection). A platform-wide Activités panel that
wants "every task everywhere" has to fan out `GET /tasks?scope=platform` to
each backend and merge client-side. `TASK-EVENT-STREAM-RFC.md` §2.9 already
describes the intended fix (`RemoteTaskClient`, central table owned by
control-plane) as "proposed," not implemented. OBSERV-02's platform Activités
panel (§2.8) just embeds the existing `TaskActivity` organism as-is, so it
inherits this limitation rather than fixing it — worth linking to OPS-04's
own tracked pending item, not a new issue.

---

## Task bus / acknowledgement (B5)

### 9. `fred-agent-evaluator` (standalone repo, not this monorepo) doesn't get ack
The evaluator has its own `TaskSummary`-shaped projection (`run_to_summary` in
`RunStore`) that mirrors the canonical `fred_core.tasks` models but never
calls the canonical `TaskService` — confirmed in the very first research pass
of this branch. Adding `acknowledged_at`/`acknowledged_by` to `TaskSummary`
is additive/backward-compatible (both default `None`), so nothing breaks —
but evaluation-kind tasks simply have no ack affordance, since that repo
can't be touched from this branch (separate repo entirely, not a path
inside `fred`). If evaluation-task acknowledgement is ever wanted, it's a
change in `fred-agent-evaluator`, not here.

### 10. `TaskRunRow.acknowledged_by` uses `String(36)`, matching `created_by`
Same column width as `created_by`/other uid columns in the same table — a
uid is a UUID string, 36 chars is the established convention here, not a new
arbitrary choice.

---

## Versions bumped so far
- `fred-core` 3.4.7 → 3.5.0 (B5: new `TaskRunRow` columns, `needs_attention()`,
  `AcknowledgeTaskResponse`, `TaskService.acknowledge`, `TaskNotAcknowledgeableError`
  — all additive, minor bump). Dependents' `fred-core>=` floors in
  `control-plane-backend`/`knowledge-flow-backend` pyproject.toml were **not**
  bumped to match — checked, and knowledge-flow's floor (`>=1.5.0`) is already
  two major versions stale, confirming this repo doesn't keep those floors
  tight in practice (both use path-based editable installs, so the floor is
  symbolic, not enforced locally). Left as-is, consistent with that norm.

---

## Runtime / capabilities (B6)

### 11. RFC §8.7's original "control-plane reads models_catalog.yaml directly" was wrong
Found while implementing, before any code was written on that assumption
(caught at design time, not as a bug fix). Control-plane has no filesystem
access to a runtime pod's mounted config in a real multi-pod deployment, and
— relevant given this platform runs multiple fred-agents replicas — nothing
guarantees every runtime source shares one catalog file even if it could.
Corrected design: fred-runtime exposes `GET /agents/models-catalog`
(mirrors the existing `GET /agents/mcp-catalog` pattern exactly), and
control-plane fetches it per runtime source, the same as it already does
for `kind="tool"`/`kind="agent"`. RFC corrected in place (§8.7).

### 12. `ModelProfile.model.provider`/`.name` are never actually optional
The RFC's field-mapping table (and my first draft of the projection
function) assumed a "local mock/test profile" could have no
provider/name and should be silently skipped. `ModelProfile.validate_model`
(`fred_runtime/model_routing/contracts.py`) already rejects any profile
missing either at construction time — the skip-branch was genuinely dead
code. Removed in favor of an `assert` that documents the invariant instead
of hiding it; caught by trying to write a test for the "skip" case, which
turned out to be impossible to construct.

### 13. `RuntimeContext.config` (`RuntimeConfig`) is not `AgentPodConfig`
Basedpyright caught this, not a runtime bug: `get_runtime_context().config`
is a distinct, generic dataclass (`RuntimeConfig`) built once at boot from
the richer `AgentPodConfig` — it does not inherit or expose
`AgentPodConfig`'s methods (`get_models_catalog_path()`). Fixed by adding a
`models_catalog_path` field to `RuntimeConfig` itself, threaded through at
the exact point `chat_model_factory` already is (same boot-time
construction call, `agent_app.py` — the established pattern for getting
pod-boot-resolved data into the generic runtime context). Worth remembering
for anyone adding a new `/agents/*` admin-catalog-style endpoint later: the
config object available at request time is `RuntimeConfig`, not
`AgentPodConfig`, and needs its own field for anything new.

### 14. `kind="model"` enforcement bootstrapping (default_on) — RESOLVED 2026-07-27, no migration built
Updated after B7 landed: the enforcement chokepoint this item was waiting on
exists and is fail-closed (see #15). Resolved by decision, not by writing the
migration: `PUT /admin/capabilities/{id}/default-on` (`set_capability_default_on`,
`enablement.py`) is already kind-agnostic — no `kind` branch anywhere in that
path — so it already works for `kind="model"` entries exactly as it does for
`tool`/`agent`, with zero code change. v1 ships with every model OFF by
default; `platform_admin` opts one in via the same admin UI/API used for any
other capability. See #15 for the operational consequence this trades in for.

---

## Runtime enforcement (B7)

### 15. ✅ RESOLVED 2026-07-27 — deployment-sequencing hazard, now a runbook step not a code gap
No team holds an explicit `can_use` grant on any `model__*` capability today
(nothing auto-seeds one — see #14). The instant ReBAC is active for a team,
`usable_model_capability_ids` returns an EMPTY set for it, and every chat
turn for that team fails closed with `ModelNotUsableError`. **Decision: no
default-on seeding migration is built for v1.** Instead, the existing
generic default-on toggle (#14) is the mechanism, and the hazard becomes an
explicit **deploy-runbook step**: on any deployment where ReBAC is already
active for at least one team, `platform_admin` must toggle default-on for
the desired model(s) (e.g. the mock-openai profile used for perf campaigns)
in the same deploy window as B7's enforcement code — before, or immediately
as, enforcement reaches that team. Skipping this step breaks all chat for
that team until the toggle is flipped by hand through `CapabilitiesPage`
(now filterable to `kind="model"` — "Frontend F5 — done" above) or the raw
API. Documented as the
resolved hazard (`CONTROL-PLANE-PRODUCT-CONTRACT.md` §17) — repeating it here
because forgetting the runbook step is exactly the kind of gap that's
invisible in code review and only shows up as a production incident; a
future auto-seeding migration remains a legitimate improvement if the manual
step proves error-prone, but is not required for this to ship.

### 16. ✅ RESOLVED 2026-08-03 (RSK-B, #2191 follow-up) — `usable_capability_ids` duplication moved into fred-core
`fred_runtime/model_routing/authz.py::usable_model_capability_ids` used to
mirror `control_plane_backend/capabilities/authz.py::usable_capability_ids`
field-for-field (same OpenFGA relations, same personal-team contextual-edge
handling) because control-plane's module could not be imported into
fred-runtime — separate deployables, no shared import path. Fixed by moving
the query logic (and its `_team_subject_and_context` helper, renamed
`team_capability_subject_and_context`) into
`fred_core.security.rebac.capability_authz` — both packages already depend
on `fred-core`. Control-plane's `authz.py` re-exports the fred-core function
under the same name (zero call-site changes across its ~10 callers);
fred-runtime's `usable_model_capability_ids` is now a thin wrapper adding
only its own `rebac is None` tolerance and `kind="model"`-prefix filter.
Exactly one copy of the query logic from here on — a future schema.fga
change to the `capability` type's `can_use` relation only needs updating
in one place.

### 17. Hot-path design decision, for the record
The naive placement (a live ReBAC check inside `ModelRoutingResolver`,
which runs multiple times per turn — once per distinct `operation`: routing,
planning, tool-call, …) would have been hotter than this platform's existing
per-request security posture. Confirmed with the developer (mid-implementation
discussion) that the fix is NOT a cache/TTL/push-sync mechanism — this
platform already rejected a control-plane-signed/cached grant design (see
`RUNTIME-EXECUTION-CONTRACT.md` §8.11) in favor of live,
never-cached, per-request pod-side OpenFGA checks. The actual fix: compute
`usable_model_capability_ids` ONCE per turn, at the same point the existing
per-request check (`_authorize_execution_or_raise`) already runs, and thread
the result through `BoundRuntimeContext` (a field explicitly documented as
the "small non-sensitive execution metadata" extension point) so every
per-operation resolution inside that turn does a local set-membership check,
zero additional network calls. One ReBAC call per turn (not per resolution),
matching the existing security model's own cost profile — not a new category
of overhead.

### 18. `ChatModelFactoryPort.build()`/`build_for_operation()` are synchronous
A real constraint, not a design choice: both methods in the shared fred-sdk
protocol are sync (not `async`), called from sync contexts
(`ModelRoutingMiddleware._resolve_model`, `GraphRuntime`'s direct `.build()`
call) — so the fail-closed check could never itself `await` a ReBAC call
even if the hot-path cost were acceptable. This is *why* the "compute once,
thread as inert data" design (#17) isn't just the efficient choice, it's the
only one the existing sync interface allows without a wider async-ification
of the model-building call chain.

---

## Frontend F5 — done (2026-07-26)

`CapabilitiesPage.tsx`'s `KIND_FILTERS` widened to `"model"` + i18n key, as
planned above. F1-F5 all shipped this pass (F6 doesn't exist — dropped with
B8, see the RFC's §2.9 correction; the dev plan only ever goes to F5).

## Two gaps found while implementing F1/F2, not part of the original plan

### 19. B3/B4 (green/cost computation) had been silently skipped
The original B1-B7 pass shipped every backend item except the green/cost
layer §2.7 calls for — no `fred-core` module, no `model_impact_factors.yaml`,
nothing wired into any token-usage preset. Unlike every other deferral in this
file, this one wasn't documented anywhere (not even in `token_usage_over_time.py`'s
own docstring, which just said "a deliberate separate follow-up pass" without
flagging that the follow-up had no tracking). Found only because F1's
green/cost widgets had nothing to render against. Implemented now:
`fred_core.kpi.model_impact_factors` (`estimate_green_cost`, YAML-configured),
wired into all six token-usage presets (platform/team/personal ×
over_time/by_agent/by_model) via a per-bucket model-name sub-aggregation so a
bucket mixing models stays exact rather than approximated.

### 20. `storage_by_team`'s platform-wide view had the wrong authorization gate
`resolve_kpi_scope` checked `can_observe_platform` uniformly for every
platform-wide preset, but RFC §2.4 requires `can_manage_platform` for the
admin-only section's presets specifically. `storage_by_team`'s unscoped call
ranks every team's storage usage — cross-team data a plain `platform_observer`
was never meant to see, and the frontend's admin-only section gate would have
been cosmetic only without this. Fixed: `PresetDef.platform_admin_only` (only
`storage_by_team`), threaded through `resolve_kpi_scope`/the router.
`team_activity_summary` is unaffected — it requires `team_id` and only ever
authorizes via `can_read_members`.

### 21. ✅ RESOLVED 2026-07-30 (by removal) — `TaskActivity`'s own rows have no ack affordance
F4 wired the real per-task ack (`POST /tasks/{id}/ack`) into `TaskCard`/
`TaskDetailPopover` — the personal tray (`TaskTray`) and `MigrationPage`. But
`TaskActivity`, embedded in `AnalyticsPage`'s and `TeamUsagePage`'s admin/editor
sections per §2.8, rendered its own inline rows, not `TaskCard`, with no dismiss
button of its own — a platform/team admin reading Activités in those dashboards
had no one-click way to acknowledge a failed row from there. Not fixed by adding
an ack affordance: those embeds turned out to duplicate the dedicated
`/admin/tasks` and `/team/:teamId/settings/activity` Activity tabs (which *do*
have ack, via `TaskCard`/`TaskDetailPopover`) one click away in the same nav
rail. Removed the embeds instead (`CONTROL-PLANE-PRODUCT-CONTRACT.md` §36) — the gap this
item tracked no longer exists because the duplicate surface it was on doesn't
either.
