---
schema: 1
title: "Add content-free ReAct and Deep LLM stream diagnostics"
impact: none
configuration: none
configuration_reason: "Adds diagnostic logs, metrics and runtime dashboard panels without changing configuration keys, timeouts, retries or concurrency defaults."
no_action_reason: "Existing storage and APIs remain compatible; telemetry is emitted through the existing logging and KPI pipeline after normal deployment."
---
## Applicability

Fred runtimes using the shared ReAct/Deep model middleware, including native Deep children. The accompanying event-loop hardening also covers cloud filesystem listings and SDK authored tools.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required. Existing observability sinks and delegation privacy settings apply. The bundled runtime dashboard includes the new panels.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

Run a ReAct or Deep request. Verify paired `llm_call_started` and `llm_call_completed` records and the `llm_calls_total` metric on the existing metrics endpoint. On an injected stream failure, the support-reference diagnostic should contain a matching failed-call snapshot. No conversation content should appear.

## Rollback

Use the normal code/dashboard rollback procedure. This change introduces no data migration.

## Limitations

The measurements cannot identify a failing network hop without gateway/provider evidence. Callback chunks are not tokens or raw wire events. Independent summarization, Graph and capability-internal LLM calls outside the shared middleware are not covered. Request IDs are absent when delegation is enabled or the upstream does not supply a permitted identifier. Abrupt process termination can prevent terminal records.

Cloud listing conversion now stays in the existing worker, and synchronous SDK
tool handlers use LangChain's context-preserving executor. Authors whose handlers
need the runtime event loop must use `async def`, as in the SDK examples. A running
synchronous handler cannot be forcibly stopped on cancellation. The model factory
also installs the narrow fragment-parser guard described in
[model configuration](../../platform/MODEL_CONFIGURATION.md#diagnosing-streaming-deadlines).
Console transport and audit retention policy are unchanged; no production
backpressure or incident root cause has been established by the local probes.
