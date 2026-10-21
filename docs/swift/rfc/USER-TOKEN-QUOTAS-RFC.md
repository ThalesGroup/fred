# RFC — Per-user token quotas

**Status:** Draft. Product decisions below are settled by the owner; the
six open questions in §5 are the only design points left before the
work is sliced into OpenSpec changes (§6).
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

- **Two gauges per user.** A **5-hour window** that opens at the user's first
  message after the previous window ended (anti-burst), and a **weekly
  window** that resets Monday 00:00 Europe/Paris. No daily gauge. A monthly
  budget is out of scope (team/platform level, later).
- **Unit: credits** = tokens x per-model coefficient. The coefficient is
  platform configuration next to the model data, never editable in the UI.
- **Admin settings stay a few numbers.** The platform admin sets one weekly
  default for everyone. The 5-hour budget is a fixed fraction of the weekly
  one (config, default 25%). The admin can search a user and set a weekly
  override (null = default), or click **"+20%"** to grant a boost valid until
  the next weekly reset.
- **Usage belongs to the user**, but every spend is tagged with the team or
  personal space where it happened. Team admins get a read-only
  "Consommation" view of spend in their team, extending the existing
  `TeamUsagePage` (`/team/{id}/usage`), not a new page.
- **User messages** at 50% and 80%. At 100%, a clean, friendly block that
  says when access returns. A turn already started always finishes; the block
  applies to the next turn.
- **One platform-wide switch.** The platform admin turns enforcement on or
  off for the whole platform. Off by default on install and upgrade, so an
  upgrading platform blocks nobody (migration impact: optional activation,
  minor). While off, spend is still written to the ledger (the team
  "Consommation" view keeps working); gauges, 50/80% messages and the 100%
  block are off. Toggling never changes the weekly default, overrides or
  active boosts.
- **Keep or reset on re-enable.** Turning enforcement back on asks: keep
  counting (current windows include everything recorded, spend while off
  included) or reset counters to 0. Reset deletes no ledger row: it stores a
  platform-wide `counters_reset_at`, and windows sum only rows after
  `max(window start, counters_reset_at)`.
- **#2528 is a prerequisite**: Deep agents must report sub-agent spend before
  quotas are enforced, or they become a quota bypass.

## 3. Proposed design

**Ledger (control-plane Postgres).** One row per completed turn:
`user_id`, `space_kind` (`team` | `personal`), `space_id`, `model_name`,
`input_tokens`, `output_tokens`, `credits`, `source` (`chat`,
`creation_assistant`, ...), `created_at`. Indexed on
`(user_id, created_at)`. Same pattern as the web-research daily quota:
insert-only rows, aggregates computed by query, safe across replicas.

**Windows.** Weekly: `sum(credits)` since the last Monday 00:00
Europe/Paris. 5-hour: the window start is the first ledger row after the
previous window ended; it is derived from the ledger (or a one-row-per-user
`window_started_at` column), never from process memory. Both windows start
at `max(window start, counters_reset_at)` when a reset baseline is set.

**Platform switch.** Reuse platform access filtering: single-row settings
with an optimistic `revision` (`PlatformAccessSettingsRow.filtering_enabled`,
`fred_core/security/platform_access/models.py:22`), `PATCH
/admin/platform/access` (`control_plane_backend/platform_access/service.py:145`),
and the `PlatformAccessPage` header badge + button opening
`PlatformAccessActivationDialog` (`PlatformAccessPage.tsx:145-170`), where the
keep/reset choice goes. Quotas get their own settings row, not access columns.

**Admission.** fred-agents already calls control-plane at every turn
(`_resolve_agent_instance` → `GET /teams/{team_id}/agent-instances/{id}/runtime`,
`product/api.py`), with user and team known, and that call already returns
409 when an instance is disabled. The quota check rides on it (skipped
while enforcement is off): if either
gauge is at or above 100%, return 409 `user_quota_exhausted` with
`resets_at`. The in-flight turn is never interrupted.

**Effective budget.** `weekly = override ?? default`, plus an active boost
(+20% of the effective weekly value, `expires_at` = next weekly reset);
`five_hour = weekly x fraction`. Settings follow the marketplace publish
quota shape (`CONTROL-PLANE-PRODUCT-CONTRACT.md`, marketplace quota section):
one default row, a nullable per-user override, 422 on invalid values.

**Frontend.** Gauges and 50/80% messages in chat; the 100% block renders the
409 `resets_at` as a friendly message. Platform-admin page reuses the
`PlatformRolesPage` user search (`GET /users`). Team view extends
`TeamUsagePage` with credits per member and per space.

## 4. Alternatives considered

- **Daily gauge.** Rejected by the owner: a weekly budget plus a 5-hour
  anti-burst window covers both fairness and spikes with fewer numbers.
- **Raw tokens as the unit.** Rejected: a token on a large model costs far
  more than one on a small model; a flat token budget either starves cheap
  models or under-protects expensive ones.
- **KPI / OpenSearch as source of truth.** Rejected: emission is best-effort
  and asynchronous, OpenSearch may be absent or lagging, and admission needs
  a transactional, multi-replica-consistent count in the database that
  control-plane already owns.
- **In-memory counters in fred-agents.** Rejected: fred-agents runs several
  replicas; per-process state silently splits the budget.

## 5. Open questions (with recommendation)

1. **Ledger shape and reporting path.** Row-per-turn table vs rolling
   counters; how fred-agents reports spend; retention.
   *Recommendation:* row-per-turn table (above), written by a small
   authenticated control-plane endpoint called at turn end from the same
   place as `_emit_turn_completed`, unless an existing turn-end call to
   control-plane can carry it. Idempotent on `(session_id, exchange_id)` so retries do not double
   count. Keep rows 90 days; aggregate older rows if the team view needs
   history (ties into #2144).
2. **Coefficient home.** `model_impact_factors.yaml` (fred-core, per
   `model_name`, default row; costs ship 0.0 per #2451) vs the model catalog
   (moving out of the agent pod per #2710).
   *Recommendation:* add a `credit_coefficient` next to each model in the
   catalog once #2710 lands it in control-plane; until then, a column in
   `model_impact_factors.yaml` with a default row of 1.0. Control-plane is the
   only reader that matters (it computes credits and remaining budget).
3. **Admission cost on the per-turn call (#3031).** Each turn adds a sum
   query to an already hot call.
   *Recommendation:* one indexed `sum` over `(user_id, created_at >= week
   start)` per turn, which also yields the 5-hour sum; measure it with the
   #3031 pool sizing. Move to a per-user rolling aggregate row only if the
   measurement shows it is needed.
4. **Spend outside a chat turn.** Creation assistant (own metric),
   `openai_compat_router.py`, knowledge-flow vision/ingestion calls.
   *Recommendation:* v1 counts chat turns (including sub-agents via #2528)
   and the creation assistant. Knowledge-flow calls are not tied to a user
   turn today; count them later, possibly at team level.
5. **How gauge state reaches the frontend.** A field on an existing response
   vs a dedicated endpoint.
   *Recommendation:* dedicated `GET /me/usage` (both gauges: used, budget,
   `resets_at`), refetched after each turn; the 409 carries `resets_at` for
   the block. Avoids widening unrelated responses. While enforcement is
   off it returns `enforced: false` and the chat shows no gauge.
6. **Does an active boost survive a counter reset?**
   *Recommendation:* yes. A reset moves the counting baseline only; boosts
   keep their `expires_at` and lapse at the next weekly reset as usual.

## 6. Slicing into OpenSpec changes

Each slice is one OpenSpec change linked to #3223, opened once §5 is
answered:

- **(a) Usage ledger + admission block** — table + migration, turn-end
  reporting, credit computation, 409 on the runtime binding call.
- **(b) Platform-admin quota page** — enforcement switch with the keep/reset
  choice on enable, weekly default, 5-hour fraction readout, per-user
  override via user search, "+20%" boost.
- **(c) User gauges + messages** — `GET /me/usage`, 50/80% notices, friendly
  100% block with the return time.
- **(d) Team "Consommation" view** — credits by member and space on
  `TeamUsagePage`, read-only, team admins only.

(a) ships first; (b), (c) and (d) depend only on (a).

## 7. Impact on contracts

- `CONTROL-PLANE-PRODUCT-CONTRACT.md`: dated entries for the ledger table,
  turn-end reporting endpoint, `user_quota_exhausted` 409 on
  `GET /teams/{team_id}/agent-instances/{id}/runtime`, quota admin endpoints
  (default, override, boost), the platform quota settings endpoint
  (`enforcement_enabled`, `counters_reset_at`; enabling takes a required
  `on_enable: keep | reset` choice), `GET /me/usage`, and the team usage
  extension.
- `RUNTIME-EXECUTION-CONTRACT.md`: "Token accounting" section and a §8 entry
  for the turn-end spend report and how a 409 quota refusal is surfaced to
  the client before a turn starts.
- `REBAC.md`: no new relation expected (platform admin and team admin
  already exist); confirm during slice (b) and (d).
- Regenerated `controlPlaneOpenApi.ts` in every slice touching the API.
