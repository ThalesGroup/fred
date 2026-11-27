---
schema: 1
title: "Count cumulative streaming LLM usage once"
impact: none
configuration: none
configuration_reason: "Only Fred's handling of streamed usage changes; model settings and deployment configuration are unchanged."
no_action_reason: "New streaming turns use corrected token counts after a normal deployment; existing data needs no migration."
---

## Applicability

Fred deployments using OpenAI-compatible Chat Completions streaming, including vLLM gateways that send cumulative usage on each chunk and Mistral streams that report usage on the finished choice.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required. `normalize_streamed_tool_call_ids: false` disables only tool-call ID correction. For Chat Completions streams, Fred ignores intermediate usage and keeps the final usage total, whether it arrives in a separate empty-choices frame or on the finished choice.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

Run a short streaming chat turn and compare its displayed and analytics token counts with the provider's final usage totals.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

Previously saved conversation and KPI counts are not recalculated. A gateway that reports usage only on unfinished chunks will not yield a count. The provider's `created_cache_tokens` detail is not currently mapped into Fred's cache-creation KPI.
