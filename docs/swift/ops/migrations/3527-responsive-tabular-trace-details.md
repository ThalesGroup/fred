---
schema: 1
title: "Keep tabular trace details responsive and show payload estimates"
impact: none
configuration: none
configuration_reason: "Only frontend rendering of recorded tool calls changes; no configuration keys, permissions or model settings change."
no_action_reason: "Existing trace parts provide the SQL, arguments and response; normal frontend deployment enables the improvement without migration or re-ingestion."
---

## Applicability

Fred deployments using managed chat's tabular tool detail drawer.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally. Existing conversations use the improved detail view without re-running their tools.

## Validation

Open a recorded tabular query with a wide response. Check that SQL appears promptly above a limited response preview, copying retains the complete original SQL/response, and separate approximate input/output token sizes appear beside status and duration. A pending output should be unavailable rather than zero.

## Rollback

Use the normal frontend rollback procedure. No persisted data or backend contract changes.

## Limitations

The badges estimate recorded payload sizes; they are not provider-exact counts or billed model usage. The visible preview omits some rows, columns and long cell contents; the response copy action retains the full recorded response.
