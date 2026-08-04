# Per-step token usage in the chat trace

**Status:** Implemented 2026-08-04 — see `RUNTIME-EXECUTION-CONTRACT.md` §8.38. The deferred rolling-overwrite undercount (§2.1) was also fixed the same day — see §8.39. Tracked in [GitHub issue #2217](https://github.com/ThalesGroup/fred/issues/2217)
**ID:** `TRACE-01` (informal)
**Author:** Maxime Daragon / Claude Code
**Date:** 2026-08-04

---

## 1. Problem statement

Each row of the chat trace (`TraceEntryRow`, under `ThoughtTrace`) shows the
latency of that tool step at the end of the line (`secondaryTextForEntry` →
`latency_ms`). There is no equivalent for token consumption — a user cannot
tell which tool call or reasoning step was expensive versus cheap, only the
conversation-level total (the top-bar badge added separately, `TRACE-XX`
n/a).

The data is *closer than it looks*: `fred-runtime`'s ReAct loop
(`react_runtime.py`) and Graph loop (`graph_runtime.py`) already capture a
`token_usage` value off every `AIMessage`/model chunk as it streams —
including the messages that decide to call a tool, not just the final
answer. Today that value is held in a rolling `last_token_usage` /
`_last_token_usage` variable that gets **overwritten at each step** and is
only ever forwarded once, attached to `FinalRuntimeEvent`. Nothing in the
runtime-event contract (`fred_sdk.contracts.runtime`) lets a per-step event
(`ToolCallRuntimeEvent`, `ThoughtStartEvent`) carry its own usage.

One additional, previously-unnoticed consequence of the same rolling
variable: because each provider's `usage_metadata` is per-call (not
cumulative — confirmed in `runtime_metadata_from_message`,
`model_metadata.py`), `FinalRuntimeEvent.token_usage` for an exchange with
multiple tool round-trips reflects only the **last** LLM call, not the sum
across the ReAct/Graph loop. The conversation-total badge in the chat top
bar (`ManagedChatPage`) is built by summing each exchange's final
`token_usage` across the thread, so it inherits this undercount whenever an
exchange makes more than one model call. Worth a decision below on whether
to fix in the same change or track separately.

---

## 2. Proposed solution

1. **Runtime (fred-runtime):** stop discarding the per-call usage. At the
   point each engine already captures a step's `token_usage` — just before
   emitting `ToolCallRuntimeEvent`/`ThoughtStartEvent` for a tool-deciding
   model call — attach it to that event instead of only updating the rolling
   `last_token_usage`. Done symmetrically in both `react_runtime.py` and
   `graph_runtime.py` — both engines in scope (see §2.1).
2. **Contract (fred-sdk):** add `token_usage: dict[str, int] | None = None`
   to `ToolCallRuntimeEvent` (and `ThoughtStartEvent`, if reasoning-phase
   usage should also be shown) in `contracts/runtime.py`. Optional, additive
   — see §4, no breaking-change risk found.
3. **OpenAPI:** thread the field through to the `tool_call` channel's
   `ChatMessage.metadata` shape — both on the live SSE payload *and* on the
   `ChatMessage` persisted by `_write_turn_history`/`make_tool_call`
   (`agent_app.py`) at the end of every turn, so the figure survives a page
   refresh or reopening a conversation created after this ships (see §2.1
   correction). Regenerate the runtime OpenAPI spec and the frontend client
   (`agenticOpenApi.ts`).
4. **Frontend:** extend `ToolResultPart`/trace metadata consumption in
   `traceUtils.ts` (mirroring how `latency_ms` is already read) and render
   it in `TraceEntryRow`, next to the existing latency in `.secondary`.

### 2.1 Scope — confirmed 2026-08-04

- **ReAct + Graph, both.** Both engines have the identical architectural
  pattern (confirmed by reading both files), so the fix is symmetric — two
  call sites, not one, but no feature-parity gap between the two agent
  types.
- **Correction (2026-08-04, after starting implementation):** "live stream
  only" was under-specified — there are two distinct reload paths, not one,
  and only one of them is actually out of scope:
  - **Conversations that finished *before* this ships** — their already-
    persisted history genuinely has no token_usage on the `tool_call`
    message. Unfixable without a backfill. **Out of scope**, unchanged: they
    keep showing latency per step (as today), not tokens.
  - **Conversations created *after* this ships** — every turn is persisted
    to the history store at the end of the exchange
    (`_write_turn_history`/`make_tool_call` in `agent_app.py`), which is the same
    path `useSessionHistory.ts` reads on a page refresh or on reopening a
    session. If this path isn't also updated, the per-step token figure
    would only exist while the answer is actively streaming and would
    silently vanish the moment the user refreshes the page — for a
    conversation from the same day. That reads as a bug, not a scope
    choice, and is **in scope**: `make_tool_call` must carry the field too,
    not just the live `ToolCallRuntimeEvent`.
  - `ThoughtRecord` (the *separate* durable record used by the eval harness,
    distinct from the `ChatMessage` history above) is still intentionally
    left untouched — genuinely a different, larger change, and not needed
    for the chat UI to work correctly.
- **The rolling-overwrite undercount (see §1) was explicitly out of scope
  for the initial change — tracked separately, not bundled in.** It changes
  the *meaning* of `FinalRuntimeEvent.token_usage` for existing consumers
  (CLI `tokens` field, eval trace `usage`, the top-bar total badge), so it
  got its own explicitly-scoped follow-up rather than riding along with an
  additive UI feature. **Fixed the same day**, once the shipped per-step
  feature made the discrepancy directly observable (summing the trace's
  per-step tokens gave a larger number than the top-bar total) — see
  `RUNTIME-EXECUTION-CONTRACT.md` §8.39.

---

## 3. Alternatives considered

- **Compute tokens client-side from characters/word count.** Rejected —
  provider tokenizers are not client-visible, any estimate would be
  systematically wrong and would misrepresent a number users may reasonably
  expect to be exact.
- **Only show the total, not per-step (status quo).** Rejected per the
  original ask — the value of this feature is pinpointing which *step* was
  expensive, which the aggregate cannot do.

---

## 4. Impact on existing contracts — breakage check

Verified directly in the source (not assumed):

| Consumer | Parsing style | Risk |
|---|---|---|
| `ToolCallRuntimeEvent`/`ThoughtStartEvent`/etc. base class (`FrozenModel`) | `ConfigDict(extra="forbid", frozen=True)` | **None found** — these classes are only ever *constructed* with kwargs in `react_runtime.py` and `graph_runtime.py` (both producers, both in fred-runtime). No consumer anywhere in the monorepo calls `.model_validate()`/`.parse_obj()` on raw event dicts to rehydrate them, so `extra="forbid"` never gets a chance to reject an unrecognized field — the strict-parsing risk flagged earlier does not materialize here. |
| `fred_runtime/cli/history_display.py`, `cli/repl.py` | Plain `dict.get(...)` on already-serialized JSON | None — tolerant by construction; a new key is silently available, not required |
| `fred_runtime/eval/collector.py` (`collect_eval_trace`) | Plain `dict.get(...)`, but **hand-picks** which keys go into each `steps[]` entry | None by default (new key silently dropped) — **but** if we choose to also surface per-step tokens in eval traces (§2, optional), `tests/test_eval_collector.py:98-103` does strict dict equality on `steps` and **will need its expected fixtures updated** — a known, not a surprise |
| `fred_runtime/app/openai_compat_router.py` | No reference to per-step event fields; only reads `token_usage` on the final chunk | None |
| `graph_runtime.py` (Graph engine) | Same producer-only construction pattern as ReAct | None — confirms both engines can take the identical fix safely |
| `ThoughtRecord` (persisted/replay) | Only constructed directly (`graph_runtime.py:349,389`), never `.model_validate()`-ed from external data | Not touched — historical replay is out of scope (§2.1) |

**Conclusion:** additive and safe as a field. The only concrete required
follow-up is `test_eval_collector.py`, and only if the eval-collector
pass-through (§2, point 3/optional) is included in the same change.

| Contract file | Change |
|---|---|
| `RUNTIME-EXECUTION-CONTRACT.md` | New optional field on `ToolCallRuntimeEvent`/`ThoughtStartEvent` — needs a dated §8 entry once implemented |
| `CONTROL-PLANE-PRODUCT-CONTRACT.md` | No change — historical replay is out of scope |

---

## 5. Out of scope (confirmed 2026-08-04, corrected same day)

- **Conversations that finished before this ships.** No retroactive
  backfill — see §2.1. Conversations created *after* this ships *are* in
  scope for persistence (corrected §2.1), only pre-existing history is
  excluded.
- **`ThoughtRecord` / eval-harness replay.** Separate durable format, not
  needed for the chat UI — see §2.1.
- **The rolling-overwrite undercount fix.** Tracked as a separate,
  independently-scoped follow-up — not bundled into this change. See §1 for
  what it is.
- Cost/CO2e estimation per step (`TokenUsageImpact` is conversation/
  team-scoped today) — no ask for this at the per-step level.
