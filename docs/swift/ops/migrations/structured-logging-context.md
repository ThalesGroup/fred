---
schema: 1
title: "Use request and operation references in API diagnostics"
impact: minor
configuration: none
configuration_reason: "Existing logging configuration is retained; HTTP completion fields and response reference headers change."
---
## Applicability

The three Fred APIs, interactive agent execution/tools, conversation creation and attachments, and upload admission.

## Prerequisites

Deploy the shared output foundation first. Custom collectors should accept the new completion fields.

## Configuration

No new configuration. Keep the selected `app.log_format`; update collector queries and log access as described below.

## Upgrade

Deploy after the shared output foundation. Update access-log queries to the `http` logger's single completion event (`http_method`, safe `route`, `http_status` when sent, `outcome`, `duration_ms`). Uvicorn access and the earlier Knowledge Flow request/response lines are suppressed. Successful probes are omitted; failures remain visible.

The message summarizes `POST /sessions/{session_id}/runs → 403 | 8ms` instead of
`HTTP request completed`. Interrupted processing appends its outcome (for example,
`200 | 8ms | disconnected`); absent route/status displays `<unmatched>`/`no response`.
Filter access events by `logger=http` and structured fields rather than the old
message text. No Grafana dashboard change is required to display the summary.

Use fresh `X-Request-ID` and `X-Correlation-ID` response headers to find a request. Generic diagnostic logs can now include admitted opaque person and resolved business references; review deployment log access and retention accordingly. Metric labels and audit restrictions remain as documented in observability §6/§7.

Request logging and configured CORS surround FastAPI's unhandled-error response
boundary, so generic 500 responses retain the references and a completion with
their actual status. Session references bind only after ownership validation or
successful creation. Batch upload completions retain batch/workflow context;
per-document references remain scoped to each file's diagnostics.

## Validation

Check normal, failing and streaming requests, a chat resume, a tool invocation, and an upload. Completion must follow stream termination, cancellation must not invent status, and unrelated requests must keep separate context. The focused offline isolation check includes actual thread work and retained tasks. Collector/deployment verification remains a rollout step.

## Rollback

Roll back this layer to restore previous access logging. No database migration or new configuration is required. Downstream and worker propagation require subsequent layers.

## Limitations

No deployment or collector canary was performed. This layer does not propagate context across services or persist ingestion context for workers; the following layers add those boundaries.
