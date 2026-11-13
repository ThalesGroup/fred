---
schema: 1
title: "Keep tabular trace details responsive"
impact: none
configuration: none
configuration_reason: "Progressive frontend rendering and retirement of unused optional tool-attribution metadata require no configuration keys, permissions or model settings changes."
no_action_reason: "Existing JSON history remains readable; normal SDK/runtime/frontend deployment requires no schema migration or re-ingestion."
---

## Applicability

Fred deployments using managed chat's tabular tool detail drawer.

## Prerequisites

Deploy the SDK/runtime and regenerated frontend normally. Established conversation usage counters remain available.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally. Existing conversations use the improved detail view without re-running their tools.

## Validation

Open a recorded tabular query with a wide response. Check that SQL appears promptly above ten JSON response rows with the existing syntax colors and every returned column. Reveal ten additional recorded rows per click, check the final remainder and action disappearance, and check that switching or reopening resets the preview. Copying must retain the complete original SQL/response, including unrevealed rows, and status and duration must retain their previous presentation. Check that full model-call usage is not displayed as individual tool consumption, including for one-row responses and after reload, and that no model-usage explanation paragraph is added. No token count should be inferred from payload length or replaced by zero when the tool API supplies none.

## Rollback

Use the normal component rollback procedure. Older readers can ignore the additive optional metadata; no schema rollback is needed.

## Limitations

The initial preview shows all columns of the first ten recorded rows, progressively reveals ten more per click, and shortens long cell contents; the response copy action retains the full recorded response. Expansion cannot retrieve rows omitted by tool result limits, and the tool-owned notice remains visible. Dedicated model-call attribution fields, extraction and runtime/history/SSE propagation introduced for tool-token display are removed. Existing conversation/billing usage and context counters remain unchanged. Old optional metadata remains readable without backfill, a database rewrite or trace lookup.
