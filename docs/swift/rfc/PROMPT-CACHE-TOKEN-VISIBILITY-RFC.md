# Prompt-cache token visibility in Fred's token-usage pipeline

**Status:** Partially implemented 2026-08-10 — extraction (§2 points 1-3) and
cost-model wiring (§2 point 4, one of six dashboard presets from point 5) are
done, see `RUNTIME-EXECUTION-CONTRACT.md` §8.45. Real per-model cached-input
rates are still unpopulated (`model_impact_factors.yaml` ships `0.0`), the
other five dashboard presets are unwired, and every §5 open question remains
unresolved — this RFC stays open until those close.
**ID:** `CACHE-01` (informal)
**Author:** CohenOdelia / Claude Code
**Date:** 2026-08-10
**Related:** `TRACE-TOKEN-USAGE-RFC.md` (per-step token usage, implemented
2026-08-04 — this RFC extends the same `token_usage` pipeline with a
breakdown LangChain already provides but Fred currently discards)

---

## 1. Problem statement

Fred already captures `token_usage` per LLM call and sums it per turn
(`RUNTIME-EXECUTION-CONTRACT.md` §8.38-8.41, `TRACE-TOKEN-USAGE-RFC.md`), and
estimates cost/CO2e/kWh from that total via
`fred_core/kpi/model_impact_factors.py` → `GreenCostEstimate`, surfaced on
`AnalyticsPage` as `TokenUsageImpact`.

That pipeline is blind to provider-side prompt caching. Concretely:

- `langchain_core.messages.ai.UsageMetadata` has carried a standardized
  `input_token_details: {cache_creation: int, cache_read: int}` breakdown
  since `langchain-core` 0.3.9 (confirmed in the vendored package —
  `langchain_core/messages/ai.py:38-71`). LangChain itself normalizes
  Anthropic's `cache_creation_input_tokens`/`cache_read_input_tokens` and
  OpenAI's `prompt_tokens_details.cached_tokens` into this one shape.
- Fred's `runtime_metadata_from_message()`
  (`libs/fred-runtime/fred_runtime/runtime_support/model_metadata.py:60-97`)
  already reads `message.usage_metadata` — the exact attribute carrying this
  breakdown — as its **first-priority** source, and passes it into
  `normalize_token_usage()`.
- But `normalize_token_usage()` (same file, lines 127-216) only extracts the
  flat `input_tokens`/`output_tokens`/`total_tokens` keys. It never looks at
  `input_token_details`, so `cache_read`/`cache_creation` are silently
  dropped at the one place they were already available.

Consequence: every input token is billed at full price in
`model_impact_factors.yaml`'s flat `cost_per_1k_*_tokens` calculation,
whether or not a cache hit occurred (providers typically bill cached reads
at a fraction of fresh-token price). This makes two things impossible today:

1. **Accurate FinOps/GreenOps numbers** — `TokenUsageImpact` overstates cost
   whenever caching is active, and there is no way to tell how much.
2. **Evaluating model-routing tradeoffs** — Fred's per-node model routing
   (`ModelRoutingPolicy`, `models_catalog.yaml`) lets an operator assign
   different models to different operations (e.g. ReAct's `routing` vs
   `planning`). Switching models mid-turn forfeits provider-side cache reuse
   at that transition point, but Fred has no data to confirm or quantify
   that loss — the question came up directly while discussing whether
   configuring `routing`/`planning` on different models could increase cost.

---

## 2. Proposed solution

1. **Runtime (fred-runtime).** Extend `normalize_token_usage()` in
   `model_metadata.py` to also read `usage.get("input_token_details", {})`
   and extract `cache_read`/`cache_creation`, defaulting to `0` when the
   provider doesn't report them (most self-hosted/OSS-served models won't).
   Source priority is unchanged — `usage_metadata` (the standardized
   LangChain attribute) is already checked first.

2. **Contract (fred-core).** Add two optional fields to `ChatTokenUsage`
   (`libs/fred-core/fred_core/history/history_schema.py:275-280`):
   `cache_read_tokens: int = 0`, `cache_creation_tokens: int = 0`. Extend
   `sum_token_usage()` to sum them the same way it sums the existing three
   fields (`None` treated as zero on either side).

3. **Runtime events.** No schema break needed — `ToolCallRuntimeEvent`/
   `FinalRuntimeEvent.token_usage` are already a `dict[str, int] | None`
   (`RUNTIME-EXECUTION-CONTRACT.md` §8.40-8.41). The two new keys ride the
   same dict, exactly as `token_usage` itself rode in additively per
   `TRACE-TOKEN-USAGE-RFC.md` §4.

4. **Cost/green model.** Add a `cost_per_1k_cached_input_tokens` column to
   `model_impact_factors.yaml`, and bill `cache_read_tokens` at that reduced
   rate instead of the full input rate in `GreenCostEstimate`. Whether a
   distinct (lower) kWh/CO2e-per-1k-cached rate is warranted is an open
   question — see §5.

5. **KPI/dashboard.** Extend the relevant control-plane KPI preset
   (`token_usage_by_model.py`) and `TokenUsageImpact` to show a cache-hit
   ratio or a cached-vs-fresh cost split, so the model-routing cost
   discussion above becomes answerable from the dashboard instead of by
   reading provider billing consoles directly.

### 2.1 Scope

- In scope: any provider LangChain already normalizes into
  `input_token_details` (Anthropic, OpenAI, and any OpenAI-compatible
  endpoint that reports `prompt_tokens_details.cached_tokens`).
- Out of scope (see §5): providers/self-hosted models that don't report
  cache detail at all — they simply keep showing `0`, same as today's
  silent behavior, not a regression.

---

## 3. Alternatives considered

- **Parse provider-specific raw fields directly** (Anthropic
  `cache_creation_input_tokens`, OpenAI `prompt_tokens_details.cached_tokens`)
  instead of relying on LangChain's already-normalized
  `input_token_details`. Rejected — LangChain has done this normalization
  consistently since `langchain-core` 0.3.9; duplicating it in Fred would
  create a second source of truth that drifts as providers change raw field
  names.
- **Estimate cache savings heuristically** (e.g. assume a fixed hit rate for
  repeated prefixes) instead of reading the provider-reported number.
  Rejected for the same reason `TRACE-TOKEN-USAGE-RFC.md` §3 rejected
  character-count token estimation: an estimate would misrepresent a number
  users may reasonably expect to be exact, when the exact number is already
  available and simply being discarded today.
- **Defer to the OTel Collector / vendor-neutral export path proposed in
  `AGENT-EVALUATION-RFC.md`.** Rejected as a blocker — that initiative is
  about evaluation/tracing export to third-party backends and is explicitly
  deferred pending proven need (`AGENT-EVALUATION-BACKLOG.md:279`). Cache
  visibility is a narrower, purely additive KPI/cost concern that doesn't
  need to wait on that broader, still-undecided initiative.

---

## 4. Impact on existing contracts — breakage check

| Contract file | Change |
|---|---|
| `RUNTIME-EXECUTION-CONTRACT.md` | New optional keys on the existing `token_usage` dict (§8.40-8.41) — needs a dated §8 entry once implemented, same pattern as §8.38-8.39. |
| `CONTROL-PLANE-PRODUCT-CONTRACT.md` | No change unless the KPI preset response shape (§2, point 5) is treated as a contract surface — confirm during implementation. |

Additive on every layer (new dict keys / new optional model fields
defaulting to `0`); no existing consumer of `token_usage` reads a fixed key
set that would choke on unrecognized keys (same pattern verified for the
`token_usage` field itself in `TRACE-TOKEN-USAGE-RFC.md` §4 — re-verify at
implementation time rather than assume it still holds).

---

## 5. Open questions (why this is still an RFC, not a compact doc)

- **Does a cached token deserve a distinct GreenOps rate, or only a cost
  rate?** Reading from cache still consumes some compute, just far less than
  a fresh forward pass — but providers don't uniformly document
  kWh/CO2e-per-cached-token. Needs input from whoever owns
  `model_impact_factors.yaml` before committing a number.
- **Do Fred's self-hosted/sovereign model profiles support prompt caching at
  all?** If not, this feature is cloud-provider-profile-only — worth being
  explicit about that in `models_catalog.yaml` rather than implying parity
  across all profiles.
- **Granularity:** dashboard-level only (§2, point 5), or also a per-step
  trace entry next to the per-step tokens `TRACE-TOKEN-USAGE-RFC.md` already
  shipped in `TraceEntryRow`? The latter is a natural extension but adds UI
  scope not yet confirmed as wanted.

---

## 6. Out of scope

- **Per-step/per-node cost/CO2e estimation in general.** Already explicitly
  out of scope per `TRACE-TOKEN-USAGE-RFC.md` §5 (`TokenUsageImpact` stays
  conversation/team-scoped); this RFC does not reopen that question, only
  adds a cache breakdown to whatever scope that estimation already has.
- **Fred actively managing cache placement** (e.g. writing explicit
  `cache_control` breakpoints for providers that require them, such as
  Anthropic). This RFC is read-only observability of caching that already
  happens server-side — opting Fred into active cache management is a
  separate, larger change with its own tradeoffs (prompt-structure
  constraints, TTL management) and would need its own RFC.
