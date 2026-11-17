---
schema: 1
title: "Log LLM provider rejection reasons and gateway correlation IDs"
impact: none
configuration: none
configuration_reason: "Model-call diagnostics read the existing provider response and use the existing delegation policy."
no_action_reason: "The new fields are additive to operational logs and require no migration or client change."
---
## Applicability

Fred Agents deployments using the shared ReAct or Deep model middleware.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally.

## Validation

For a gateway rejection with `detail: "OASValidation"`, check that `llm_call_completed`
contains `provider_error_name=OASValidation`. When the gateway returns
`x-correlation-id` and delegation is disabled, check for `x_correlation_id` on
the same record. The identifier must contain at most 128 ASCII identifier
characters. Provider reasons come only from a fixed allowlist, including
`content_filter`, `context_length_exceeded`, and `OASValidation`; raw provider
messages, prompts and response bodies are not logged by this diagnostic.
These two new fields are excluded from model spans and Prometheus labels.
The existing `execution_error.llm_failures` snapshot can also carry them.

## Rollback

Use the normal rollback procedure.

## Limitations

Both fields depend on the upstream response. Previously collected logs retain
their original fields. With delegation enabled, upstream request and correlation
identifiers are omitted; provider categories remain available. This note describes
the implementation; deployed provider and log-collector reception remains required.
