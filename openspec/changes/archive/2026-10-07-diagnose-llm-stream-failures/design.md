## Context

See proposal.md for scope. Investigation uses local swift `9b2b5162afe1578788f34728a1dc5f4a338cbacc`, not an asserted deployment version.

### Evidence and limits

- Both supplied October 5 traces pass through Deep's native `subagents.atask`, the child model call, Fred's `tracing_kpi.py`, and the OpenAI-compatible streaming reader. The failure surfaces through `tool_execution.py`; this is not evidence that a business tool or the browser SSE connection failed.
- Integration: `StreamChunkTimeoutError`, model `mistral`, 120 seconds, 1,971 SDK chunks already received. The nested `CancelledError` is the pending read cancelled by `asyncio.wait_for`, not evidence of user cancellation. Chunks are not tokens. No context-limit rejection is shown.
- Production: `httpx.RemoteProtocolError` while reading an HTTP/1.1 chunked response. The peer closed before completing HTTP framing. This identifies the observed failure, not which upstream hop caused it.
- A local loopback HTTP server with the installed ChatOpenAI reproduced both signatures: one valid SSE event followed by silence (50 ms chunk deadline) produced `StreamChunkTimeoutError` with `chunks_received=1`; closing the connection without the terminating HTTP chunk produced the exact incomplete-body `RemoteProtocolError`. This is dependency-level fault injection, not reproduction of the reported Deep workload.
- `TracingKpiMiddleware` emits total `llm.call_latency_ms` (including an error status), start/response size logs and span status, but no streaming progress/error breakdown. Parent and child share the binding; `child=True` currently selects HITL behavior but does not reach this middleware.
- `report_execution_error` intentionally excludes exception values and retains classes/frames. Safe numeric timeout attributes are consequently absent from its support record.
- Core defaults are connect/read/write/pool = 10/120/30/5 seconds and SDK max_retries=0. Shared HTTP pool tuning is first-initialization-wins; the factory forwards an effective request timeout. LangChain's chunk deadline is a separate setting. These are code defaults, not verified deployed settings.
- Local runtime lock records langchain-openai 1.3.2, deepagents 0.7.19 and httpx 0.28.1. Raw socket bytes, decoded SDK events, LangChain callbacks and visible answer tokens are different observation layers.

Provider stall/load, gateway idle or absolute deadlines, upstream restart, and local event-loop delay remain hypotheses. Long tasks and child concurrency can increase exposure without being the defect themselves. Existing `event_loop_lag_ms` and process KPIs must be included when testing these hypotheses.

## Goals / Non-Goals

Provide a support-reference-to-failed-call path and enough chronology to prioritize an infrastructure investigation. Keep the existing observability ownership and privacy rules. A chunk gap measured in Fred cannot prove network silence or provider responsibility. Non-goals are listed in proposal.md.

## Decisions

### One call-local collector at the existing boundary

Extend `TracingKpiMiddleware`, using a supported LangChain callback attached to a call-local Runnable configuration and a per-call state object. Never mutate the cached/shared model callback list or keep mutable progress on the middleware instance. Compose existing callbacks and run the handler in the copied configuration context; keep the model itself intact, including stateful custom models. Derive root/child role from runtime assembly and retain the native run/parent relationship where available; missing ancestry is explicitly unknown, never guessed from a shared agent id.

Use monotonic clocks and constant-space counters: first/last callback time, observed chunk count, maximum gap and terminal silence. Count empty/tool/reasoning callbacks as progress; do not inspect or retain their content. Callbacks update memory only: no log or KPI per chunk and no worker dispatch per token. Do not monkey-patch LangChain's private iterator. Consequently name these measurements `observed_chunks`, not wire chunks or token counts. Preserve the SDK's separate `chunks_received` when the exception provides it.

An opaque `llm_call_id` identifies each middleware invocation, including each existing Fred retry attempt. Emit one start and one terminal record. Preserve parent invocation/native run identifiers in diagnostic channels under the existing privacy policy; no raw user/session/team identity is added. A failure snapshot follows the exception to `report_execution_error` through a bounded, cycle-safe cause/group walk, allowing the existing `error_ref` record to name the failing call(s). Limit collected children and mark truncation. Cancellation propagates unchanged and finalization runs exactly once.

### Bounded error and configuration data

Classify exceptions without parsing free text: `stream_idle_timeout`, transport `connect_timeout/read_timeout/write_timeout/pool_timeout`, `remote_protocol_error`, `connection_error`, `rate_limited`, `provider_http_error`, `cancelled`, `unknown`. Traverse explicit causes and applicable contexts/groups with bounded depth; prioritize the outer chunk timeout over its inner read cancellation. Record bounded exception class, numeric timeout/count/status fields and failure stage (`before_first_chunk`, `streaming`, `non_streaming`, `unknown`). Unknown fields remain absent, never inferred as zero.

Log a safe effective configuration snapshot once per effective model configuration: provider/model, streaming flag, chunk deadline, phase timeouts, SDK retry count and shared connection limits; log installed relevant versions once per process. Derive effective values from constructed objects/tuning rather than dumping YAML or environment. Replace the existing DEBUG `effective_settings` dump with the allow-listed snapshot in the touched path.

For OpenAI-compatible HTTP requests, use shared-client response hooks with call-local context to capture response-header arrival time, HTTP status and only validated, length-bounded `x-request-id`/`apim-request-id` values when present. Do not enable wholesale response-header capture, read the body in hooks, change pooling or log URL/header dictionaries. The transport metadata is best-effort and is absent for unsupported providers. Provider IDs remain diagnostic-only and respect delegation restrictions. No assumption that a gateway forwards the provider's original ID.

### Extend existing KPIs and dashboard

Keep `llm.call_latency_ms` compatible. Add a terminal call counter with fixed dimensions (`model_name`, closed `llm_role`, `status`, closed `error_code`) and first-observed-chunk, maximum-gap and terminal-silence histograms in milliseconds, plus active-call gauge per process/model/role. Success uses error_code `none`; all dimensions are present from first emission. Missing observations produce no fabricated timing sample. Record request message/tool/character counts once per call in diagnostics using existing size helpers; use provider token usage only when supplied and mark missing usage unknown.

Extend the explicit Prometheus allow-list only for the closed role dimension. Call/native/provider IDs, settings fingerprints and exception messages never become labels. Reuse the existing bounded service/model labels. Include finite histogram buckets beyond 120 seconds for the new long-call timings without broadening unrelated metrics or claiming #2533 is solved.

Extend `deploy/grafana/fred-agent-runtime.json` with error rate by category/role/model, first-chunk and gap distributions, active calls and existing loop-lag/process panels. Provide queries for support reference → call → upstream request id and incident timestamps in the existing observability guide. Teach operators to compare time-since-call-start against time-since-last-progress: a repeatable total lifetime suggests an absolute deadline; a repeatable silence interval suggests an idle limit. These remain hypotheses requiring gateway/provider evidence.

## Risks / Trade-offs

- Callback observations miss raw keepalives and filtered SDK events → name the layer, keep SDK counts separate; no claim of packet-level diagnosis.
- Concurrent native children share models/bindings → per-call state and interleaving tests, supported callback composition, no global identity registry.
- Telemetry can alter timing or fail → constant-space updates, existing resilient sinks, tests that sink failure preserves original outcomes and no per-chunk I/O.
- Correlation may expose identifiers under delegation → generated technical IDs only and explicit tests for both delegation settings; exclude unapproved upstream IDs when required.
- Existing model middleware does not cover Deep summarization's independent calls, arbitrary capability calls or all Graph paths → state coverage explicitly in docs; do not present dashboard totals as all provider billing.
- Low-frequency loop-lag sampling can miss a short stall → diagnostic correlation is supporting evidence, not an exclusion of local causes.

## Migration Plan

After scope confirmation, create the issue and dedicated branch. Deliver additive telemetry and matching dashboard/docs with an English migration note; keep runtime policy unchanged. Deploy to integration, exercise injected faults and a long Deep run, then compare production under the same model/configuration. Roll back code/dashboard together if telemetry creates overhead; no data migration is needed.

## Open Questions

The deployed image digests, effective settings, gateway timeout policy and provider-side request records are not available. They are needed to attribute the incidents, not to implement the agreed instrumentation. The user selected current swift as the investigation reference.
