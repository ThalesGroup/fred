---
schema: 1
title: "Preserve Knowledge Flow MCP failure diagnostics"
impact: none
configuration: none
configuration_reason: "The existing in-process MCP client and logging configuration are reused."
no_action_reason: "Deploying the updated Knowledge Flow image enables the diagnostics without data migration."
---

## Applicability

Knowledge Flow MCP tools and tabular discovery/description on Weaver.

## Prerequisites

Deploy the matching Knowledge Flow and shared-core packages.

## Configuration

No configuration changes are required.

## Upgrade

Failed inner MCP HTTP calls now emit `mcp.inner_http_failure` with method, route,
status, and validated request/correlation IDs. Empty tabular discovery logs
`tabular.discovery_empty` with counts observed during its existing paginated
lookup. Missing spreadsheet catalog logs `tabular.description_failure` with a
closed reason. Tool error responses continue to follow Weaver's existing
redaction and authority-loss policy.

## Validation

Check the structured log events while triggering a failed MCP call, an empty
tabular selection, or a missing published spreadsheet catalog. The diagnostic
fields must contain no request body, SQL, document name, or response body.

## Rollback

Roll back the Knowledge Flow image. No stored state changes.

## Limitations

Counts describe only the documents traversed by the current request.
