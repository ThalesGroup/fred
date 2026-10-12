## Why

Long Deep runs in integration and production fail while consuming an LLM stream. Current Fred telemetry reports overall model latency and a support reference but cannot reliably distinguish a first-chunk wait, a mid-stream stall, a truncated response, or a local cancellation, or identify the failing child call among concurrent sub-agents.

## What Changes

- Extend the existing ReAct/Deep model observability boundary with content-free, correlated start/completion/failure diagnostics and constant-space streaming progress measurements.
- Preserve safe structured timeout attributes and the failed model-call identity in support diagnostics, including errors propagated through Deep's `task` tool.
- Record effective model/transport settings and installed dependency versions without dumping configuration, URLs, headers or secrets.
- Expose bounded error categories, first-chunk latency, maximum observed chunk gap, terminal silence and active model calls through existing KPI plumbing and the runtime Grafana dashboard; reuse existing event-loop lag and process measurements.
- Prove the behavior using offline streaming fault injection, concurrent Deep children, cancellation and privacy tests.

## Capabilities

### New Capabilities

- `llm-call-observability`: diagnostic lifecycle and streaming measurements for the shared ReAct/Deep model boundary, including native Deep children. No existing main spec owns this cross-runtime capability; the compact observability document retains the cross-stream privacy rules.

### Modified Capabilities

None. The existing `deep-agent-runtime-baseline` change concerns dispatch, capability wiring and HITL and only awaits historical close-out; this independently reviewable diagnostic outcome does not reopen it.

## Impact

- `libs/fred-runtime`: existing tracing/KPI middleware, Deep parent/child attribution, support-error reporting and focused tests.
- `libs/fred-core`: effective model settings, HTTP response metadata hooks where needed, KPI metric definitions/Prometheus label filtering and tests.
- `deploy/grafana/fred-agent-runtime.json`, the existing observability/model configuration guides and an English release migration note.
- No new public API, storage service, dependency, prompt capture or agent execution policy.
- Planning reference: local `swift` at `9b2b5162a`. Tracking: [#2988](https://github.com/ThalesGroup/fred/issues/2988), branch `2988-investigate-deep-llm-stream-failures-and-improve-diagnostic-telemetry` in the existing checkout. Implementation scope confirmed by the developer on 2026-10-07. Related but separate: #2531 (Deep concurrency), #2528 (child token accounting), #2533 (histogram units).

## Non-goals

Changing timeouts, retrying broken streams, modifying concurrency limits, repairing context budgeting, changing user-facing errors, or claiming the production root cause has been reproduced. Graph and capability-internal LLM calls outside this middleware are explicitly excluded from first-slice coverage.
