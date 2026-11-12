---
schema: 1
title: "Keep tabular trace details responsive"
impact: none
configuration: none
configuration_reason: "Optional model-call usage metadata and bounded frontend rendering require no configuration keys, permissions or model settings changes."
no_action_reason: "Existing JSON history stores optional usage metadata; normal SDK/runtime/frontend deployment requires no schema migration or re-ingestion."
---

## Applicability

Fred deployments using managed chat's tabular tool detail drawer.

## Prerequisites

Deploy the updated SDK/runtime before the regenerated frontend to capture new API model-call counters.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally. Existing conversations use the improved detail view without re-running their tools.

## Validation

Open a recorded tabular query with a wide response. Check that SQL appears promptly above a limited JSON response preview with its existing syntax colors, copying retains the complete original SQL/response, and status and duration retain their previous presentation. Check API-model input/output badges against a recorded provider response and reload the conversation. Missing counters must remain unavailable, and parallel tools must not multiply billing totals. No token count should be inferred from payload length.

## Rollback

Use the normal component rollback procedure. Older readers can ignore the additive optional metadata; no schema rollback is needed.

## Limitations

The visible preview omits some rows, columns and long cell contents; the response copy action retains the full recorded response. Counters cover the first LLM exchange after the tool result, including full context, rather than the requesting model call or isolated SQL execution. Historical rows without recorded counters remain unavailable; no automatic production backfill or trace lookup is introduced.
