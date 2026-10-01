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

Use fresh `X-Request-ID` and `X-Correlation-ID` response headers to find a request. Generic diagnostic logs can now include admitted opaque person and resolved business references; review deployment log access and retention accordingly. Metric labels and audit restrictions remain as documented in observability §6/§7.

## Validation

Check normal, failing and streaming requests, a chat resume, a tool invocation, and an upload. Completion must follow stream termination, cancellation must not invent status, and unrelated requests must keep separate context. The focused offline isolation check includes actual thread work and retained tasks. Collector/deployment verification remains a rollout step.

## Rollback

Roll back this layer to restore previous access logging. No database migration or new configuration is required. Downstream and worker propagation require subsequent layers.
