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

Open a recorded tabular query with a wide response. Check that SQL appears promptly above a limited JSON response preview with its existing syntax colors, copying retains the complete original SQL/response, and status and duration retain their previous presentation. Check that full model-call usage is not displayed as individual tool consumption, including for one-row responses and after reload, and that no model-usage explanation paragraph is added. No token count should be inferred from payload length or replaced by zero when the tool API supplies none.

## Rollback

Use the normal component rollback procedure. Older readers can ignore the additive optional metadata; no schema rollback is needed.

## Limitations

The visible preview omits some rows, columns and long cell contents; the response copy action retains the full recorded response. Model-call usage includes full prompts/completions and does not measure an individual tool. The drawer omits such counters; the current tabular API supplies no per-tool token breakdown. Optional model metadata remains available through existing history/API data. No automatic production backfill or trace lookup is introduced.
