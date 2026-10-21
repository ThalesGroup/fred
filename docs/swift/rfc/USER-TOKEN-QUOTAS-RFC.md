# RFC — Per-user token quotas

**Status:** Draft — pending team review. Product decisions (§2) are settled
by the owner; design in §3; one open point (§5). Once reviewed, each slice in
§6 moves to an OpenSpec change.
**Author:** Maxime Daragon
**Date:** 2026-10-21
**Tracking:** #3223 (epic). Prerequisite for blocking: #2528.
**Related:** #3031, #2710 (model catalog home), #2451 (empty cost tile),
#2156, #2144, `TEAM-PLATFORM-POLICY-RFC.md` (excludes billing budgets),
`openspec/specs/web-research/spec.md` (daily per-user quota precedent)

---

## 1. Problem

Fred has no limit on one person's LLM usage: a single user (or a Deep agent
fanning out sub-agents) can exhaust the provider budget for everyone. Token
counts are best-effort telemetry and incomplete: `_parse_turn_outcome`
(`libs/fred-runtime/fred_runtime/app/agent_app.py:3469`) reads the final
event only (one `model_name`, no `cache_creation_tokens`), so stopped,
cancelled or failed turns, model calls inside tools (`ctx.extract_structured`,
`fred_sdk/authoring/api.py:288`, document access) and sub-agent spend
(#2528) are lost. There is no shared count admission can check.

## 2. Decided

**Gauges, prices and credits**
- **Two gauges per user:** a **5-hour window** and a **weekly window**
  resetting Monday 00:00 Europe/Paris. No daily gauge; no monthly budget.
- **Real prices:** the platform admin keeps a per-model table of input and
  output prices in € per million tokens. Cache reads cost a technical 10% of
  the input price (platform config, not in the admin UI); cache creation
  costs the input price.
- **Credits are the single user-facing unit**, replacing tokens wherever
  usage is shown: **1 € = 10,000 credits**, platform config, not
  admin-editable (a change would silently revalue every quota). A Mistral
  Medium turn (~10k in + ~800 out) ≈ 0.006 € ≈ 60 credits, a Small turn
  ≈ 10, so integer display loses ≤ ~5%. Example: 5 € = 50,000 credits a
  week, 5-hour budget 25% = 12,500.
- **Exact values, display rounding only:** computation and storage are exact
  decimals; the UI rounds to the nearest credit, minimum 1 for any non-zero
  spend (never "0 credits").
- **Users never see euros.** Platform and team admins see both ("50 000
  crédits · 5,00 €"), plus tokens where meaningful (analytics charts).
- **Unpriced model:** loud admin alert; its spend is charged at the most
  expensive priced model's price until a price is entered (no free hole).
- **Long conversations are the main driver** (the history is resent every
  turn): the Help Center advises a new conversation when changing topic.

**Admin settings**
- The platform admin sets one weekly default and, via user search, a weekly
  override (null = default). The 5-hour budget is a fixed fraction (config,
  default 25%) of the **effective weekly quota, active boost included**.
- Quotas, overrides and the per-turn ceiling are stored and entered in
  credits, with the € equivalent shown live; the boost stays a percentage.
- **Platform admins are under quota like everyone.** Override `0` = blocked;
  no "unlimited" value (use a large override); a platform admin can set any
  override, their own included. Local/dev config ships a high default.

**"+20%" boost**
- Granted by the platform admin, or by a team admin to a member of their
  team **at most once per user per week across all teams** (then platform
  admin only). A team admin cannot boost themselves. Not cumulative.
- +20% of the user's effective weekly quota (override if any, else default).
- Expires at `max(next weekly reset, granted_at + 24h)`, so a late boost
  lasts at least 24 h; survives a counters reset.
- Revocable; visible in the user's gauge; audited (who, when).
- Granted from the quota page's users table (platform admin) or the team
  "Consommation" page's member search (team admin, "+20%" button).

**Who pays**
- **The authenticated identity decides, not the endpoint.** A person using
  their own token pays on every path: chat, shared or marketplace agents,
  team spaces, `/agents/evaluate`, the OpenAI-compatible API, the creation
  assistant. The team/space tag is for reporting only.
- Only service identities with no person behind them (service agents,
  scheduled/Temporal runs, M2M) are exempt. They are still written to the
  ledger with a **server-set `source`**, never trusted from the caller.

**Availability**
- **Fail-open.** If admission cannot reach control-plane or exceeds its
  timeout, the turn runs; a metric and an alert fire. Platform access, by
  contrast, fails closed (`platform_access/access_control.py:206`, 503).

**User experience**
- **Chat badge** per message shows credits; input/output tokens on hover.
- **Composer indicator** left of the model selector, always visible while
  tracking is on. It shows a % or an icon besides colour (accessibility;
  visual to iterate). Levels: normal / 50% / 80% / 100%; the popover shows
  "used / budget credits", window and reset time.
- The 50%, 80% and tracking-only over-quota tooltips open **once per
  window**; dismissible. At 100% with blocking on, a friendly block message
  says when access returns.
- Existing design tokens and molecules only (`Tooltip`, `Dialog`, ...).
- A started turn always finishes (bounded by the per-turn ceiling, so a turn
  admitted at 99% can spend one ceiling; Help Center says so); HITL resumes
  are never blocked.

**Team "Consommation" view**
- Extends `TeamUsagePage` (`/team/{id}/usage`), read-only, team admins only.
- Team totals, breakdown by agent and by model. **No per-member spend.**
  Credits and euros from the ledger; KPI charts labelled as token analytics.
- **Teams under 3 members: totals hidden** (platform config), with: "Totals
  are hidden for teams with fewer than 3 members, to protect each member's
  privacy."

**Platform switches** (roll out tracking first, block later)
- **Usage tracking**: indicator and tooltips, `GET /me/usage` state, team
  credits view, over-quota notice at 100%.
- **Blocking**: refuses turns at 100% (structured 409) and enables the
  per-turn ceiling. Requires tracking; turning tracking off turns blocking
  off.
- Both off on install and upgrade (optional activation, minor). The ledger
  records spend in every state; toggling never changes quotas or boosts.
- Turning either switch on asks: keep counting, or reset counters to 0
  (zeroes every counter row, stores `counters_reset_at`; ledger untouched).

**Release gate: complete counting before blocking**
- The server refuses the blocking switch until the per-model-call
  accumulator (§3) covers Stop/cancel/error, tool-internal model calls and
  sub-agents (#2528). Tracking may ship earlier with a known under-count,
  stated in the UI and the Help Center.

**Scope boundaries**
- **Known v1 bypass:** knowledge-flow ingestion, vision and embedding calls
  are not counted.
- Team ceilings stay out of scope (`TEAM-PLATFORM-POLICY-RFC.md`); a later
  team budget would cap, not replace, per-user quotas.

## 3. Proposed design

**Credit formula.** Per model call, with per-model prices `p_in`, `p_out`
in € per million tokens, platform `cache_read_rate` (0.1) and
`credits_per_euro` (10,000):
`credits = (input x p_in + output x p_out + cache_read x p_in x cache_read_rate + cache_creation x p_in) / 1e6 x credits_per_euro`.
- Exact `NUMERIC` arithmetic (no floats). `input` is uncached input: the
  accumulator normalises providers whose `input_tokens` include cache reads.
- Unpriced model: most expensive priced model's price (config fallback if
  none is priced), admin alert and metric.

**Model price table (control-plane Postgres).** One row per `model_name`:
`input_eur_per_mtok`, `output_eur_per_mtok`, `updated_by`, `updated_at`;
admin-editable, audited, seeded from chart values for models with no row
(the table then wins). Models listed: the catalog (#2710 decides its home)
plus any `model_name` seen in the ledger without a price.
- **It replaces the `cost_per_1k_*` fields** of
  `fred_core/kpi/model_impact_factors.yaml` (USD, all 0.0 today, hence
  #2451's empty "Estimated cost" tile). The KPI presets run in
  control-plane, so `estimate_green_cost` reads this table (same fallback)
  and reports euros; the YAML keeps only co2e/kWh. Slice (b), closes #2451.

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
`cache_creation_tokens`, prices applied (`p_in`, `p_out`,
`cache_read_rate`), exact `credits` (`NUMERIC`), `source`
(`chat`, `creation_assistant`, `evaluation`, `openai_compat`, `service`,
`scheduled`, `m2m`; server-set), `user_anonymised` (bool), `created_at`.
- Unique `(session_id, exchange_id, run_id, model_name)`. `run_id` is
  minted per request because a HITL resume reuses the exchange_id
  (`_resolve_exchange_id`, `agent_app.py:3687`): each resume is its own
  segment, retries of one report never double count.
- No-person rows: `source` `service`/`scheduled`/`m2m`, `user_id` null. A
  deleted user's rows get `user_id` null, `user_anonymised = true`.
- Index `(user_id, created_at)`. The ledger is the history (team view,
  audit, retention); admission reads the counters below, never the ledger.
- The runtime reports raw tokens; control-plane computes credits at write
  with the prices in force. Retention 90 days (KPI keeps its own).
- Failed reports retry with the unique key; a metric counts final failures.

**Running counters (control-plane Postgres).** One row per user:
`window_started_at`, `window_credits` (5-hour) and `week_started_at`,
`week_credits`, exact `NUMERIC`. Never in process memory.
- Each spend report adds to both windows in the same transaction as its
  ledger insert, in one statement, safe across replicas:
  `SET window_credits = CASE WHEN window expired THEN x ELSE window_credits + x END, window_started_at = CASE WHEN window expired THEN now() ELSE window_started_at END`
  (same shape for the week). A retried report that hits the ledger unique
  key adds nothing.
- 5-hour: starts with the first spend after the previous window ended,
  `resets_at = window_started_at + 5h`. Weekly: Monday 00:00 Europe/Paris.
  A missing row or expired window reads as 0.
- An admin maintenance job rebuilds drifted counters from ledger rows after
  `max(window start, counters_reset_at)`.

**Effective budget.** `weekly = (override ?? default) + active boost`;
`five_hour = weekly x fraction`. Settings follow the marketplace publish
quota shape (`CONTROL-PLANE-PRODUCT-CONTRACT.md`): one default row, a
nullable per-user override (`>= 0`), 422 on invalid values. Boost rows carry
`granted_by`, `granted_at`, `revoked_by`, `revoked_at`, `expires_at`; the
team-admin weekly limit is a count on these rows across all teams, and a
grant where `granted_by == user_id` by a team admin is refused.

**Admission on every entry point.** The `/runtime` binding call is not
enough: `_resolve_agent_instance` (`agent_app.py:1777`) returns early for a
direct `request.agent_id`. A dedicated admission call (one primary-key read
added to the per-turn control-plane call, #3031) runs whatever the switch
state on `POST /agents/execute` and `/agents/execute/stream` (managed
instance and direct `agent_id`), `/agents/evaluate`, the OpenAI-compatible
router (`openai_compat_router.py:267`) and `POST /creation-assistant/draft`.
HITL resumes are not checked.

It returns `{admitted, ceiling | null, prices | null}`: blocking, the
ceiling and the price snapshot (incl. the unpriced fallback) are fixed for
the turn at admission. Replicas never cache the switches; turns already
running when blocking turns on carry no ceiling (accepted). On timeout or
unreachable control-plane: admitted, no ceiling (fail-open). Refusal: HTTP
409 `code: user_quota_exhausted` (distinct from the instance-disabled 409),
`window`, `resets_at`, before the stream opens.

**Per-turn ceiling.** Platform config in credits, returned by admission
only while blocking is on, with the price snapshot the runtime needs to
convert its accumulator (prices live in control-plane). Checked between
model and sub-agent calls; when hit, the turn ends cleanly with a message.
Parallel turns can overshoot, bounded by concurrent turns x ceiling.

**Platform switches.** Reuse the platform access pattern: one settings row
with an optimistic `revision` (`PlatformAccessSettingsRow`,
`fred_core/security/platform_access/models.py:22`) and a PATCH like
`/admin/platform/access`. Quotas get their own row (`tracking_enabled`,
`blocking_enabled`): blocking without tracking is a 422, disabling tracking
clears blocking, blocking is refused until the release gate (§2). The
keep/reset choice is a new small dialog on the central `Dialog` molecule.

**Observability.** Audit events for override set/clear, boost
grant/revoke, price edits, switch toggles, counters reset. Metrics for
blocks, 50/80% warnings, ceiling hits, admission fail-open (with alert),
failed spend reports, spend on unpriced models (with alert); Grafana panels.

**Frontend.** Indicator fed by `GET /me/usage` (both windows: used,
budget, `resets_at`, active boost; `tracking`, `blocking`), refetched after
each turn; once-per-window tooltip state keyed by window start.
`TokenUsageBadge` shows the exchange's credits (sum of its ledger rows,
added to the message usage, which carries tokens only today), ↑/⚡/↓ tokens
in the tooltip; the `ManagedChatPage` header total switches to credits too.
One shared formatter rounds (nearest, minimum 1) and renders the admin
"credits · €" pair. The chat and the OpenAI-compatible client map the 409
`code` to the block message. The admin page reuses the `PlatformRolesPage`
user search (`GET /users`); the team page searches team members only.

## 4. Alternatives considered

- **Daily gauge.** Rejected: weekly + 5-hour anti-burst covers both.
- **Raw tokens.** Rejected: models, output and cache reads differ in cost.
- **Abstract per-model coefficients.** Rejected: admins cannot relate them
  to money; real € prices also feed the estimated-cost KPI.
- **1 credit = 1 cent.** Rejected: a typical turn would be under 1 credit.
- **Euros shown to users.** Rejected: credits keep money out of the chat.
- **Final-event usage as the source.** Rejected: misses Stop/cancel/error,
  tool-internal calls, sub-agents and cache creation.
- **KPI / OpenSearch or in-memory counters.** Rejected: best-effort or
  split across replicas; admission needs a transactional shared count.
- **Quota check only on the `/runtime` binding call.** Rejected: direct
  `agent_id` and OpenAI-compatible runs never make that call.
- **Exemption by endpoint** (`/agents/evaluate`). Rejected: a bypass.
- **Fail-closed admission.** Rejected: a ledger outage would stop all chat.

## 5. Open questions

- **Home "Responsible AI" tile** (`ResponsibleAiSection`) shows the user's
  token count next to its environmental estimate: switch it to credits like
  the chat, or keep tokens because the tile is about energy, not budget?
  Other implementation details are decided inside each OpenSpec change.

## 6. Slicing into OpenSpec changes

Each slice is one OpenSpec change linked to #3223:

- **(a) Ledger + counters + accumulator + admission + ceiling** —
  accumulator at the model client, ledger and counter tables + migration
  (`run_id` key), exact-decimal credits from config-seeded prices, counter
  rebuild job, idempotent exit-path reporting, fail-open admission on every
  entry point (`{admitted, ceiling, prices}`), ceiling, structured 409,
  switches seeded off. Also: migration note (minor), chart values +
  schemas (seed prices, `cache_read_rate`, `credits_per_euro`, unpriced
  fallback, 5-hour fraction, ceiling, admission timeout, high dev default),
  audit events, metrics, Grafana panels.
- **(b) Platform-admin quota page** — model price table (€/M tokens,
  unpriced alert; KPI estimated cost reads it in €, closes #2451), switches
  (server-side rules, keep/reset `Dialog`), default and overrides in credits
  with live €, users table with boost grant/revoke; boost API incl.
  team-admin scope (once per user per week across teams, no self-boost).
- **(c) Composer indicator and credits in chat** — `GET /me/usage`,
  indicator and "used / budget credits" popover, once-per-window tooltips,
  over-quota notice or 100% block; `TokenUsageBadge` and header total in
  credits; fr+en Help Center (credits, windows, ceiling at 99%, under-count
  while counting is incomplete, new conversation when changing topic).
- **(d) Team "Consommation" view** — ledger totals by agent and model in
  credits and €, hidden under 3 members with the privacy message, member
  search with the "+20%" button, KPI charts labelled as token analytics.

Order: (a) → (b) → (c); (d) once (a) and the boost API from (b) are in.
**Release gate:** blocking cannot be enabled until the accumulator (incl.
#2528) is merged.

## 7. Impact on contracts

- `CONTROL-PLANE-PRODUCT-CONTRACT.md`: dated entries for the ledger,
  counter and price tables, price admin endpoints, spend reporting,
  admission (`{admitted, ceiling, prices}`, 409 `code:
  user_quota_exhausted`), quota admin endpoints (default, override, boost
  incl. team-admin scope), quota settings (`tracking_enabled`,
  `blocking_enabled`, 422 rules, `counters_reset_at`, `on_enable: keep |
  reset`), `GET /me/usage`, per-exchange credits on message usage, the team
  usage extension, KPI `cost_usd` becoming euros.
- `RUNTIME-EXECUTION-CONTRACT.md`: "Token accounting" section and a §8 entry
  for the accumulator, admission on every entry point (fail-open), the
  ceiling ending a turn, exit-path reporting with `run_id`, and how the 409
  reaches the client before the stream (chat SSE and
  `openai_compat_router.py`).
- Frontend: composer error handling for the 409 `code`.
- `REBAC.md`: no new relation expected; confirm the team-admin boost scope
  in slice (b).
- `OBSERVABILITY-AND-AUDIT.md`: new audit events, metrics, alerts.
- `KPI-ANALYTICS-RFC.md` §2.7 / `model_impact_factors.yaml`: cost fields
  removed; prices come from the control-plane table.
- Regenerated `controlPlaneOpenApi.ts` in every slice touching the API.
