# OBSERV-02 v3 — follow-up notes (not this branch's scope)

Working notes kept alongside issue #2110 while implementing `KPI-ANALYTICS-RFC.md`
v3. Each entry below is something found *while building*, deliberately left out
of this branch, and worth its own small GitHub issue later. Not a design doc —
just enough context per entry to write that issue without re-deriving it.

---

## Backend — KPI presets

### 1. `documents_total` cannot be team-scoped without new store-layer work
`document.created_total`/`document.deleted_total` KPI events DO carry
`dims.team_id` (knowledge-flow resolves it from the document's first tag
owner — `features/metadata/service.py:824`), but `PostgresDocumentMetadataStore`
has no team-scoped count, and a document's team is indirect (via tag
ownership, not a column). Team-scoping this preset needs a real store method,
not just a query parameter. Left `team_scopable=False` with a comment in
`kpi/presets/documents_total.py`.

### 2. `agent_prompt_length_distribution` — data available, not wired
`agent.created_total` carries `dims.team_id` (same as `agents_total`), so this
*could* be team-scoped the same way — but the preset runs 3 separate queries
(created/deleted/alive-with-prompt-length) and deserves a careful pass rather
than a rushed one. Deferred, `team_scopable=False`, comment in the file.

### 3. `active_users_over_time` / `unique_users_total` — architecturally blocked
Sourced from `api.request_latency_ms` (the generic HTTP middleware KPI),
which deliberately never carries `dims.team_id` (`KPI-ANALYTICS-RFC.md` §2.2
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
content — noted in `KPI-ANALYTICS-RFC.md` §2.8 as explicitly out of scope for
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

## Runtime / capabilities (expected to grow once B6/B7 start)

*(nothing yet — will fill in as B6/B7 progress)*
