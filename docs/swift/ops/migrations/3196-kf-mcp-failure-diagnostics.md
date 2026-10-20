---
schema: 1
title: "Preserve Knowledge Flow MCP failure diagnostics"
impact: none
configuration: none
configuration_reason: "The dedicated in-process MCP client uses existing delegation and logging settings; no configuration, dependency version or HTTP schema changes."
no_action_reason: "Normal shared-core and Knowledge Flow image deployment enables the diagnostics. No data migration, re-ingestion, permission changes or client updates are required."
---

## Applicability

Knowledge Flow first-party MCP mounts and tabular discovery/description.

## Prerequisites

Use the normal matched Fred images with the updated shared-core package.
The existing fastapi-mcp 0.4.0 pin remains unchanged.

## Configuration

No configuration changes are required. Existing JSON/text and optional generic
log-store settings apply. No metrics or identity label dimensions are added.

## Upgrade

Deploy normally. Ordinary failed MCP tools now return upstream error text with
the tool name, inner HTTP status and response detail instead of the blanket
"Tool request failed." message. This includes the curated read_query HTTP 400
SQL detail. The authority refusal result remains
`isError=true, structuredContent={"cause":"authority_lost"}`, so the runtime
still stops the run. HTTP route responses and agent presentation policy are unchanged.

## Validation

Trigger an invalid read_query SQL column against an authorized dataset. The
outer MCP call can return HTTP 200 while the tool result is an error containing
HTTP 400 and the curated SQL detail. Find `mcp.inner_http_failure` in the JSON
`message` field, then join its `upstream_request_id` to the inner HTTP access
record. Check delegated user/run/agent and available session/team context.
The diagnostic must contain no SQL or response body. Dependency diagnostics
remain sanitized and console-only, including when debug logging is enabled.

Empty tabular discovery emits `tabular.discovery_empty` with a closed reason
and observed stage counts. Expected description 404s emit
`tabular.description_failure` with a distinct resolution/preview reason.
See the existing observability guide for reason definitions and a GCP query.

## Rollback

Roll back shared-core and Knowledge Flow images normally. No stored documents,
conversations or authorization state change. The previous blanket MCP failure
message and less detailed diagnostics return.

## Limitations

This does not resolve the historical workbook incident, change agent-side
logging/presentation, introduce retries, or validate production GCP collection.
Resolution counts describe work already performed, not a global corpus census.
