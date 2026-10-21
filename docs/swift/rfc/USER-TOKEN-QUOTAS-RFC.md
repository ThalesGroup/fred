# RFC — Per-user token quotas

**Status:** Draft. Product decisions (§2) are settled by the owner and the
independent review findings are folded into §3; the three open questions in
§5 are the only design points left before the work is sliced into OpenSpec
changes (§6).
**Author:** Maxime Daragon
**Date:** 2026-10-21
**Tracking:** #3223 (epic). Prerequisite: #2528.
**Related:** #3031, #2710, #2451, #2156, #2144, `TEAM-PLATFORM-POLICY-RFC.md`
(excludes billing budgets), `openspec/specs/web-research/spec.md` (daily
per-user quota precedent)

---

## 1. Problem

Fred has no limit on how much LLM usage one person can consume. On a shared
deployment, a single user (or a Deep agent fanning out sub-agents) can
exhaust the provider budget or rate limits for everyone. Token counts exist
today only as best-effort telemetry: `_emit_turn_completed` in
`libs/fred-runtime/fred_runtime/app/agent_app.py` emits them to KPI /
OpenSearch, and `ChatTokenUsage`
(`libs/fred-core/fred_core/history/history_schema.py`) stores them with the
history. Neither is a ledger that admission can count against, sub-agent
spend is dropped (#2528), and the creation assistant and knowledge-flow LLM
calls are not tied to a user turn at all.

## 2. Decided

**Gauges and unit**
- **Two gauges per user.** A **5-hour window** and a **weekly window** that
  resets Monday 00:00 Europe/Paris. No daily gauge; a monthly budget is out
  of scope.
- **Unit: credits** = tokens x per-model coefficient, platform configuration
  next to the model data, never editable in the UI.

**Admin settings**
- The platform admin sets one weekly default. The 5-hour budget is a fixed
  fraction of the weekly one (config, default 25%). The admin can search a
  user and set a weekly override (null = default).
- **"+20%" boost.** Granted by the platform admin, or by a team admin to a
  member of their team **at most once per user per week**; beyond that only
  the platform admin can grant.
  - Not cumulative: a second grant while one is active does nothing.
  - +20% of the user's effective weekly quota (override if any, else default).
  - Revocable; visible in the user's gauge; audited (granted by whom and
    when, revoked by whom and when).
  - Expires at the next weekly reset, and survives a counters reset.

**Who pays**
- The user who runs the turn pays, on their personal quota, including with
  shared or marketplace agents and in a team space. The team/space tag is for
  reporting only.
- Runs with no person behind them (evaluations, service agents,
  scheduled/Temporal runs, M2M) are not charged in v1, but are written to the
  ledger with their `source`.

**User experience**
- **Composer indicator** immediately left of the model selector, always
  visible while tracking is on (also before the first message). Its colour
  follows the alert level: normal / 50% / 80% / 100%.
- At 50% and 80%, a coloured tooltip opens above the indicator when the
  threshold is crossed; dismissible. Hover shows details: used %, which
  window, reset time.
- At 100%: with blocking on, a friendly block message says when access
  returns; with blocking off, the same indicator's tooltip says the quota is
  exceeded and the turn still runs.
- Existing design tokens and molecules only (`Tooltip`, ...): no new CSS
  custom properties.
- A turn already started always finishes (bounded by the per-turn ceiling,
  §3); HITL resumes (ask_user, plan approval) are never blocked.

**Team "Consommation" view**
- Extends `TeamUsagePage` (`/team/{id}/usage`), read-only, team admins only.
- Team totals and breakdown by agent and by model. **No per-member
  breakdown** (privacy).

**Platform switches** (roll out tracking first, block later)
- **Usage tracking**: composer indicator and tooltips, `GET /me/usage`
  state, team "Consommation" credits view, over-quota notice at 100%.
- **Blocking**: refuses turns at 100% (structured 409) and enables the
  per-turn ceiling. Only possible while tracking is on; turning tracking off
  also turns blocking off.
- Both off by default on install and upgrade (migration impact: optional
  activation, minor). The ledger records spend in every state. Toggling never
  changes the default, overrides or active boosts.
- Turning either switch on asks: keep counting, or reset counters to 0 (e.g.
  enable blocking with a fresh start so nobody is blocked at once). Reset
  deletes no ledger row: it stores `counters_reset_at`, and windows sum only
  rows after `max(window start, counters_reset_at)`.

**Scope boundaries**
- **#2528 is a prerequisite**: Deep agents must report sub-agent spend before
  quotas are enforced, or they become a quota bypass.
- **Known v1 bypass:** knowledge-flow ingestion, vision and embedding calls
  are not counted.
- Team ceilings stay out of scope (`TEAM-PLATFORM-POLICY-RFC.md`); a later
  team budget would cap, not replace, per-user quotas.

## 3. Proposed design

**Ledger (control-plane Postgres).** One insert-only row per turn and model: `user_id`
(null for no-person runs), `space_kind` (`team` | `personal`), `space_id`,
`agent_id`, `model_name`, `session_id`, `exchange_id`, raw `input_tokens`,
`output_tokens`, `cache_read_tokens`, `cache_creation_tokens`, the
coefficient(s) applied, `credits`, `source` (`chat`, `creation_assistant`,
`evaluation`, `service`, `scheduled`, `m2m`), `created_at`.
- Unique `(session_id, exchange_id, model_name)`: the idempotency key, so
  retries never double count.
- Index `(user_id, created_at)`; aggregates computed by query, safe across
  replicas (web-research quota pattern).
- Credits computed at write with the coefficient in force: a mid-week
  coefficient change only affects new rows.
- A model missing from the coefficient config: loud warning, default
  coefficient, metric.
- Retention: 90 days. KPI analytics keep their own retention.

**Windows.**
- Weekly: `sum(credits)` since the last Monday 00:00 Europe/Paris.
- 5-hour: starts at the admission time of the first turn after the previous
  window ended; `resets_at = window_start + 5h`. Stored as one row per user
  (`window_started_at`), never in process memory.
- Both start at `max(window start, counters_reset_at)` when a reset is set.

**Effective budget.** `weekly = (override ?? default) + active boost`;
`five_hour = weekly x fraction`. Settings follow the marketplace publish
quota shape (`CONTROL-PLANE-PRODUCT-CONTRACT.md`): one default row, a
nullable per-user override, 422 on invalid values. Boost rows carry
`granted_by`, `granted_at`, `revoked_by`, `revoked_at`, `expires_at`; the
team-admin weekly limit is a count on these rows.

**Admission on every entry point.** A quota check riding only on the
`/runtime` binding call is not enough: `_resolve_agent_instance`
(`agent_app.py:1777`) returns at ~1802-1832 for a direct `request.agent_id`
without calling control-plane. A dedicated control-plane quota admission
call (skipped unless blocking is on) runs on each execute entry point:
- `POST /agents/execute` and `/agents/execute/stream`, managed instance
  (`agent_instance_id`) and direct `agent_id`;
- the OpenAI-compatible router (`openai_compat_router.py:267`, direct
  `agent_id = request.model`);
- the creation assistant (`POST /creation-assistant/draft`).
- `/agents/evaluate` and no-person runs are not checked (not charged).
- HITL resumes are not checked.

Refusal: HTTP 409 with a structured `code: user_quota_exhausted` (distinct
from the existing instance-disabled 409), `window` and `resets_at`, returned
before the stream opens.

**Per-turn ceiling.** Platform config: max credits per turn, applied only
while blocking is on. The runtime
checks accumulated turn spend between LLM and sub-agent calls; when hit, the
turn ends cleanly with a message to the user. Parallel turns (several tabs)
can overshoot the quota, bounded by concurrent turns x per-turn ceiling;
accepted for v1.

**Spend reporting.** fred-agents reports spend to an authenticated
control-plane endpoint on every exit path (success, error, cancel, abort,
via `finally` / cancel handlers), from the same place as
`_emit_turn_completed`. Failed reports retry with the idempotency key; a
metric counts reports that finally fail.

**Platform switches.** Reuse the platform access filtering pattern:
single-row settings with an optimistic `revision`
(`PlatformAccessSettingsRow.filtering_enabled`,
`fred_core/security/platform_access/models.py:22`), `PATCH
/admin/platform/access` (`control_plane_backend/platform_access/service.py:145`),
and `PlatformAccessActivationDialog` (`PlatformAccessPage.tsx:145-170`) for
the keep/reset choice. Quotas get their own settings row with
`tracking_enabled` and `blocking_enabled`. The server enforces the
dependency: a PATCH enabling blocking while tracking is off is a 422, and
disabling tracking clears blocking in the same write.

**Observability.** Audit events for override set/clear, boost grant/revoke,
tracking and blocking toggles, counters reset. Metrics for blocks, 50/80%
warnings, per-turn ceiling hits, failed spend reports, unknown-model
coefficients.

**Frontend.** Composer indicator and tooltip fed by `GET /me/usage` (both
windows: used, budget, `resets_at`, active boost; `tracking: false` hides
the indicator, `blocking: false` turns the 100% block into the over-quota
notice), refetched after each turn. The chat and the OpenAI-compatible
client map the 409 `code` to the block message. Platform-admin page reuses
the `PlatformRolesPage` user search (`GET /users`).

**Consommation figures.** Credits come from the ledger only. The existing KPI
charts stay on the page, labelled as token analytics, never mixed into credit
totals.

## 4. Alternatives considered

- **Daily gauge.** Rejected by the owner: a weekly budget plus a 5-hour
  anti-burst window covers both fairness and spikes with fewer numbers.
- **Raw tokens as the unit.** Rejected: a token on a large model costs far
  more than one on a small model.
- **KPI / OpenSearch as source of truth.** Rejected: best-effort and
  asynchronous, may be absent or lagging; admission needs a transactional,
  multi-replica-consistent count.
- **In-memory counters in fred-agents.** Rejected: several replicas silently
  split the budget.
- **Quota check only on the `/runtime` binding call.** Rejected: direct
  `agent_id` and OpenAI-compatible runs never make that call.

## 5. Open questions (with recommendation)

1. **Input vs output pricing.** One coefficient per model, or separate input
   and output coefficients (or an output multiplier); how cache tokens count.
   *Recommendation:* separate `input` and `output` coefficients per model
   (output defaults to input when unset), cache reads at the input rate.
   Home: `model_impact_factors.yaml` (fred-core, default row 1.0) until #2710
   moves the catalog to control-plane, then next to each catalog model.
2. **Admission cost (#3031).** Each turn adds a sum query to a hot path.
   *Recommendation:* one indexed `sum` over `(user_id, created_at >= week
   start)` per admission, which also yields the 5-hour sum; measure with the
   #3031 pool sizing; move to a rolling aggregate row only if needed.
3. **User deletion.** What happens to a deleted user's ledger rows.
   *Recommendation:* anonymise `user_id` (set null), keep rows so team
   totals stay correct until retention removes them.

## 6. Slicing into OpenSpec changes

Each slice is one OpenSpec change linked to #3223, opened once §5 is
answered:

- **(a) Ledger + admission** — table + migration, credit computation,
  spend reporting on every exit path with idempotent retry, dedicated quota
  admission on every execute entry point, per-turn ceiling in the runtime,
  structured 409 before the stream, audit events and metrics.
- **(b) Platform-admin quota page** — tracking and blocking switches
  (dependency enforced server-side, keep/reset on each enable), weekly
  default, 5-hour fraction readout, per-user override via user search,
  boost grant/revoke; team-admin boost for their members (once per user per
  week).
- **(c) Composer indicator** — `GET /me/usage` with `tracking`/`blocking`
  state, indicator left of the model selector, threshold tooltip, over-quota
  notice (tracking only) or friendly 100% block with the return time.
- **(d) Team "Consommation" view** — ledger credit totals by agent and by
  model on `TeamUsagePage`, no per-member breakdown, KPI charts labelled as
  token analytics.

(a) ships first; (b), (c) and (d) depend only on (a).

## 7. Impact on contracts

- `CONTROL-PLANE-PRODUCT-CONTRACT.md`: dated entries for the ledger table,
  the spend reporting endpoint, the quota admission endpoint and its 409
  `code: user_quota_exhausted`, quota admin endpoints (default, override,
  boost grant/revoke incl. team-admin scope), the platform quota settings
  endpoint (`tracking_enabled`, `blocking_enabled` with its 422 dependency
  rule, `counters_reset_at`, required `on_enable: keep | reset` whenever a
  switch turns on), `GET /me/usage` (`tracking`, `blocking`), and the team
  usage extension.
- `RUNTIME-EXECUTION-CONTRACT.md`: "Token accounting" section and a §8 entry
  for admission on every execute entry point, the per-turn ceiling ending a
  turn, exit-path spend reporting, and how the 409 reaches the client before
  the stream (chat SSE client and `openai_compat_router.py` error mapping).
- Frontend: composer error handling for the 409 `code`.
- `REBAC.md`: no new relation expected (platform admin and team admin
  already exist); confirm the team-admin boost scope during slice (b).
- `OBSERVABILITY-AND-AUDIT.md`: new audit events and metrics, Grafana-visible.
- Regenerated `controlPlaneOpenApi.ts` in every slice touching the API.
