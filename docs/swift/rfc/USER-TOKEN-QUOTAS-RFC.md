# RFC — Per-user token quotas

**Status:** Draft. Product decisions (§2) are settled by the owner; both
independent review rounds and the gauge formula are folded into §3. The
questions in §5 are the only design points left before the work is sliced
into OpenSpec changes (§6).
**Author:** Maxime Daragon
**Date:** 2026-10-21
**Tracking:** #3223 (epic). Prerequisite for blocking: #2528.
**Related:** #3031, #2710, #2451, #2156, #2144, `TEAM-PLATFORM-POLICY-RFC.md`
(excludes billing budgets), `openspec/specs/web-research/spec.md` (daily
per-user quota precedent)

---

## 1. Problem

Fred has no limit on one person's LLM usage: a single user (or a Deep agent
fanning out sub-agents) can exhaust the provider budget for everyone. Token
counts are best-effort telemetry and incomplete: `_parse_turn_outcome`
(`libs/fred-runtime/fred_runtime/app/agent_app.py:3469`) reads the final
event only (one `model_name`, no `cache_creation_tokens`), so stopped,
cancelled or failed turns, model calls inside tools (`ctx.extract_structured`,
`fred_sdk/authoring/api.py:288`, document access) and sub-agent spend
(#2528) are lost. There is no ledger admission can count against.

## 2. Decided

**Gauges and unit**
- **Two gauges per user.** A **5-hour window** and a **weekly window** that
  resets Monday 00:00 Europe/Paris. No daily gauge; no monthly budget.
- **Unit: credits**, computed per model call (formula in §3). Coefficients
  are platform configuration next to the model data, never editable in the UI.
- **Long conversations are the main driver**: the whole history is resent as
  input every turn. The Help Center advises starting a new conversation when
  changing topic.

**Admin settings**
- The platform admin sets one weekly default. The 5-hour budget is a fixed
  fraction (config, default 25%) of the **effective weekly quota, active
  boost included**. The admin can search a user and set a weekly override
  (null = default).
- **Platform admins are under quota like everyone.** Override `0` = blocked
  (valid). There is no "unlimited" value: use a large override. A platform
  admin can set any override, their own included.
- Testing needs high quotas: local/dev configuration ships a high default
  weekly quota.

**"+20%" boost**
- Granted by the platform admin, or by a team admin to a member of their
  team **at most once per user per week across all teams**; beyond that only
  the platform admin can grant. A team admin cannot boost themselves.
- Not cumulative: a second grant while one is active does nothing.
- +20% of the user's effective weekly quota (override if any, else default).
- Expires at `max(next weekly reset, granted_at + 24h)`, so a late boost
  lasts at least 24 h; survives a counters reset.
- Revocable; visible in the user's gauge; audited (granted/revoked by whom
  and when).
- The quota tooltip offers **"Request a boost"**, notifying the admins who
  can grant it: team admins of the team the user is working in, and platform
  admins. The delivery channel is a slice (b)/(c) detail.

**Who pays**
- **The authenticated identity decides, not the endpoint.** A person using
  their own token pays on every path: chat, shared or marketplace agents,
  team spaces, `/agents/evaluate`, the OpenAI-compatible API, the creation
  assistant. The team/space tag is for reporting only.
- Only service identities with no person behind them (service agents,
  scheduled/Temporal runs, M2M) are exempt. They are still written to the
  ledger with a **server-set `source`**, never trusted from the caller.

**Availability**
- **Fail-open.** If the admission call cannot reach control-plane/the
  ledger, or exceeds its timeout budget, the turn runs; a metric and an
  alert fire. This deliberately differs from platform access, which fails
  closed (`fred_core/security/platform_access/access_control.py:206`, 503).

**User experience**
- **Composer indicator** immediately left of the model selector, always
  visible while tracking is on (also before the first message). It shows a
  % or an icon besides colour (accessibility; the visual will be iterated).
  Levels: normal / 50% / 80% / 100%.
- The 50%, 80% and tracking-only over-quota tooltips open **once per
  window**, not every turn; dismissible. Hover shows used %, window, reset
  time.
- At 100% with blocking on, a friendly block message says when access
  returns.
- Existing design tokens and molecules only (`Tooltip`, `Dialog`, ...).
- A turn already started always finishes (bounded by the per-turn ceiling,
  §3); HITL resumes are never blocked. A turn admitted at 99% can still
  spend up to one ceiling: the Help Center says so.

**Team "Consommation" view**
- Extends `TeamUsagePage` (`/team/{id}/usage`), read-only, team admins only.
- Team totals, breakdown by agent and by model. **No per-member view.**
  Credits from the ledger; KPI charts labelled as token analytics.

**Platform switches** (roll out tracking first, block later)
- **Usage tracking**: indicator and tooltips, `GET /me/usage` state, team
  credits view, over-quota notice at 100%.
- **Blocking**: refuses turns at 100% (structured 409) and enables the
  per-turn ceiling. Requires tracking; turning tracking off turns blocking
  off.
- Both off on install and upgrade (optional activation, minor). The ledger
  records spend in every state. Toggling never changes the default,
  overrides or active boosts.
- Turning either switch on asks: keep counting, or reset counters to 0.
  Reset deletes no row: it stores `counters_reset_at`, and windows sum only
  rows after `max(window start, counters_reset_at)`.

**Release gate: complete counting before blocking**
- Blocking can only be enabled once the per-model-call accumulator (§3) is
  in: Stop/cancel/error paths, tool-internal model calls, sub-agents
  (#2528). Until then the server refuses the blocking switch.
- Tracking may ship earlier with a known under-count, stated in the UI and
  the Help Center.

**Scope boundaries**
- **Known v1 bypass:** knowledge-flow ingestion, vision and embedding calls
  are not counted.
- Team ceilings stay out of scope (`TEAM-PLATFORM-POLICY-RFC.md`); a later
  team budget would cap, not replace, per-user quotas.

## 3. Proposed design

**Credit formula.** Per model call, with per-model `c_in`, `c_out` and a
platform `cache_read_rate`:
`credits = input x c_in + output x c_out + cache_read x c_in x cache_read_rate + cache_creation x c_in`.
- Defaults follow public API pricing ratios: `c_out` ~5x `c_in`,
  `cache_read_rate` ~0.1.
- `input` is uncached input: the accumulator normalises providers whose
  `input_tokens` already include cache reads, so nothing is counted twice.
- Home: `model_impact_factors.yaml` (fred-core, default row) until #2710
  moves the catalog to control-plane, then next to each catalog model.
- Unknown model: loud warning, default coefficients, metric.

**Per-turn accumulator (fred-runtime).** Counting happens at the model
client (callback/wrapper), not from the final event, so every call is
seen: the agent loop, tool-internal calls (`ctx.extract_structured`,
document access) and sub-agents (same prerequisite as #2528). It splits
usage per model, feeds the per-turn ceiling, and is reported on every exit
path (success, error, Stop/cancel, abort, via `finally` / cancel handlers),
from the same place as `_emit_turn_completed`.

**Ledger (control-plane Postgres).** One insert-only row per model per run
segment: `user_id`, `space_kind` (`team` | `personal`), `space_id`,
`agent_id`, `model_name`, `session_id`, `exchange_id`, `run_id`, raw
`input_tokens`, `output_tokens`, `cache_read_tokens`,
`cache_creation_tokens`, coefficients applied, `credits`, `source`
(`chat`, `creation_assistant`, `evaluation`, `openai_compat`, `service`,
`scheduled`, `m2m`; server-set), `user_anonymised` (bool), `created_at`.
- Unique `(session_id, exchange_id, run_id, model_name)`. `run_id` is
  minted per request because a HITL resume reuses the exchange_id
  (`_resolve_exchange_id`, `agent_app.py:3687`): each resume is its own
  segment, retries of one report never double count.
- No-person rows are identified by `source` (`service`, `scheduled`, `m2m`),
  with `user_id` null. A deleted user's rows get `user_id` null and
  `user_anonymised = true`, kept so team totals stay correct until retention.
- Index `(user_id, created_at)`; aggregates by query, safe across replicas
  (web-research quota pattern).
- Credits computed at write with the coefficients in force.
- Retention: 90 days. KPI analytics keep their own retention.
- Failed reports retry with the unique key; a metric counts final failures.

**Windows.**
- Weekly: `sum(credits)` since the last Monday 00:00 Europe/Paris.
- 5-hour: the window starts when spend is written, i.e. at the first ledger
  row after the previous window ended, whatever the switch state;
  `resets_at = window_start + 5h`. Stored as one row per user
  (`window_started_at`), never in process memory.
- Both start at `max(window start, counters_reset_at)` when a reset is set.

**Effective budget.** `weekly = (override ?? default) + active boost`;
`five_hour = weekly x fraction`. Settings follow the marketplace publish
quota shape (`CONTROL-PLANE-PRODUCT-CONTRACT.md`): one default row, a
nullable per-user override (`>= 0`), 422 on invalid values. Boost rows carry
`granted_by`, `granted_at`, `revoked_by`, `revoked_at`, `expires_at`; the
team-admin weekly limit is a count on these rows across all teams, and a
grant where `granted_by == user_id` by a team admin is refused.

**Admission on every entry point.** A check riding on the `/runtime` binding
call is not enough: `_resolve_agent_instance` (`agent_app.py:1777`) returns
early for a direct `request.agent_id`. A dedicated control-plane admission
call runs on every execute entry point, whatever the switch state (one
indexed query):
- `POST /agents/execute` and `/agents/execute/stream`, managed instance and
  direct `agent_id`; `/agents/evaluate`;
- the OpenAI-compatible router (`openai_compat_router.py:267`);
- the creation assistant (`POST /creation-assistant/draft`).
- HITL resumes are not checked.

It returns `{admitted, ceiling | null}`: blocking and the ceiling are fixed
for the turn at admission. Replicas never cache the switches; turns already
running when blocking turns on carry no ceiling (accepted). On timeout or
unreachable control-plane: admitted, no ceiling (fail-open). Refusal: HTTP
409 `code: user_quota_exhausted` (distinct from the instance-disabled 409),
`window`, `resets_at`, before the stream opens.

**Per-turn ceiling.** Platform config, returned by admission only while
blocking is on. The runtime checks the accumulator between model and
sub-agent calls; when hit, the turn ends cleanly with a message. Parallel
turns can overshoot, bounded by concurrent turns x ceiling; accepted.

**Platform switches.** Reuse the platform access pattern: a single settings
row with an optimistic `revision` (`PlatformAccessSettingsRow`,
`fred_core/security/platform_access/models.py:22`) and a PATCH like
`/admin/platform/access` (`control_plane_backend/platform_access/service.py:145`).
Quotas get their own row with `tracking_enabled`, `blocking_enabled`. The
server enforces dependencies: blocking while tracking is off is a 422,
disabling tracking clears blocking in the same write, and blocking is
refused until the release gate (§2) is met. `PlatformAccessActivationDialog`
is an eligible-users preview without keep/reset, so the keep/reset choice is
a new small dialog on the central `Dialog` molecule.

**Team privacy (recommended).** Team totals are hidden for teams below a
minimum member count (e.g. 3), so a total cannot be read as one person's
spend.

**Observability.** Audit events for override set/clear, boost
grant/revoke/request, switch toggles, counters reset. Metrics for blocks,
50/80% warnings, ceiling hits, admission fail-open (with alert), failed
spend reports, unknown-model coefficients; Grafana panels.

**Frontend.** Indicator and tooltip fed by `GET /me/usage` (both windows:
used, budget, `resets_at`, active boost; `tracking`, `blocking`), refetched
after each turn; once-per-window tooltip state keyed by window start. The
chat and the OpenAI-compatible client map the 409 `code` to the block
message. The admin page reuses the `PlatformRolesPage` user search
(`GET /users`).

## 4. Alternatives considered

- **Daily gauge.** Rejected: a weekly budget plus a 5-hour anti-burst window
  covers fairness and spikes with fewer numbers.
- **Raw tokens, or one coefficient per model.** Rejected: model sizes,
  output (~5x input) and cache reads (~0.1x) differ by large factors.
- **Final-event usage as the source.** Rejected: misses Stop/cancel/error,
  tool-internal calls, sub-agents and cache creation.
- **KPI / OpenSearch or in-memory counters.** Rejected: best-effort or
  split across replicas; admission needs a transactional shared count.
- **Quota check only on the `/runtime` binding call.** Rejected: direct
  `agent_id` and OpenAI-compatible runs never make that call.
- **Exemption by endpoint** (`/agents/evaluate`). Rejected: a bypass.
- **Fail-closed admission.** Rejected: a ledger outage would stop all chat.

## 5. Open questions (with recommendation)

1. **Admission cost (#3031).** One more query on every turn's hot path.
   *Recommendation:* one indexed `sum` over `(user_id, created_at >= week
   start)` that also yields the 5-hour sum; load test in slice (a); a
   rolling aggregate row only if the test requires it.
2. **Team privacy threshold.** Hide team totals below N members.
   *Recommendation:* N = 3, platform config.
3. **Boost request delivery.** In-app notification, e-mail, or both.
   *Recommendation:* in-app notification to team admins of the current team
   and platform admins, decided in slice (b)/(c).

## 6. Slicing into OpenSpec changes

Each slice is one OpenSpec change linked to #3223:

- **(a) Ledger + accumulator + admission + ceiling** — per-model-call
  accumulator at the model client, ledger table + migration with `run_id`
  key, credit formula, exit-path reporting with idempotent retry, fail-open
  admission on every entry point returning `{admitted, ceiling}`, per-turn
  ceiling, structured 409, switch effects seeded off. Also: migration note
  (minor), chart values + regenerated schemas (coefficients,
  `cache_read_rate`, 5-hour fraction, ceiling, admission timeout, high dev
  default), audit events, metrics and Grafana panels, load test of the
  admission query.
- **(b) Platform-admin quota page** — switches (dependencies and release
  gate server-side, keep/reset dialog on `Dialog`), weekly default, 5-hour
  fraction readout, overrides via user search, boost grant/revoke incl.
  team-admin scope (once per user per week across teams, no self-boost).
- **(c) Composer indicator** — `GET /me/usage`, indicator with % or icon,
  once-per-window tooltips, over-quota notice or 100% block, "Request a
  boost"; fr+en Help Center pages (credits, windows, ceiling at 99%,
  under-count while counting is incomplete, start a new conversation when
  changing topic).
- **(d) Team "Consommation" view** — ledger totals by agent and model,
  minimum-member threshold, KPI charts labelled as token analytics.

Order: (a) → (b) → (c); (d) in parallel once (a) is in. **Release gate:**
the blocking switch cannot be enabled until the accumulator (incl. #2528)
is merged.

## 7. Impact on contracts

- `CONTROL-PLANE-PRODUCT-CONTRACT.md`: dated entries for the ledger table,
  the spend reporting endpoint, the admission endpoint (`{admitted,
  ceiling}`, 409 `code: user_quota_exhausted`), quota admin endpoints
  (default, override, boost grant/revoke/request incl. team-admin scope),
  the quota settings endpoint (`tracking_enabled`, `blocking_enabled`, 422
  rules, `counters_reset_at`, `on_enable: keep | reset`), `GET /me/usage`,
  and the team usage extension.
- `RUNTIME-EXECUTION-CONTRACT.md`: "Token accounting" section and a §8 entry
  for the accumulator, admission on every entry point (fail-open), the
  ceiling ending a turn, exit-path reporting with `run_id`, and how the 409
  reaches the client before the stream (chat SSE and
  `openai_compat_router.py`).
- Frontend: composer error handling for the 409 `code`.
- `REBAC.md`: no new relation expected; confirm the team-admin boost scope
  in slice (b).
- `OBSERVABILITY-AND-AUDIT.md`: new audit events, metrics, alert.
- Regenerated `controlPlaneOpenApi.ts` in every slice touching the API.
