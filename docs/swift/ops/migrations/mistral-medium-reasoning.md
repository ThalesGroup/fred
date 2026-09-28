---
schema: 1
title: "Enable Mistral Medium reasoning in the agent model catalogs"
impact: minor
configuration: production
configuration_reason: "The Fred chart now includes a Mistral Medium profile with reasoning_effort and top_p. Using it requires a Mistral credential and the existing model enablement settings."
---

## Applicability

Local Fred developers and deployments using the bundled fred-agents model
catalog. The Helm chart adds `chat.mistral.medium`; its default chat profile
remains `default.chat.openai.prod`.

## Prerequisites

To select Mistral Medium in a deployed agent pod, provide a Mistral API key as
`applications.fred-agents.dotenv.OPENAI_API_KEY`. The bundled GPT and Mistral profiles do not override `api_key`, so they
share `OPENAI_API_KEY` within a pod. A pod configured with a Mistral key cannot
also call the bundled GPT profiles; use a separate agent pod if both providers
are needed.

## Configuration

The bundled local and Helm profiles declare `supports_thinking: true` and send
`reasoning_effort: high` when the platform admin enables reasoning for this
model. Both set `top_p: 1.0` because the shared `temperature: 0.0` setting uses
greedy sampling. Keep Mistral Medium unselected on pods with an OpenAI key.

## Upgrade

Deploy the updated chart normally. To activate Medium, configure the Mistral
credential on its agent pod, select the `chat.mistral.medium` profile for the
intended agent or team, and enable reasoning for the model in platform admin.
Existing selection and reasoning settings do not change automatically.

## Validation

Confirm the rendered `models_catalog.yaml` contains the Medium profile with
`supports_thinking: true`, `reasoning_effort: high`, and `top_p: 1.0`. Complete
a short chat turn with reasoning enabled and confirm no model API error occurs.

## Rollback

Select the previous model and disable Medium reasoning in platform admin, or
restore the prior chart/catalog. No data migration is involved.

## Limitations

The bundled GPT and Mistral profiles share `OPENAI_API_KEY`, so they cannot
use different credentials in one pod without custom credential handling.
Deployments overriding the bundled model catalog must add this profile to
their own values to receive the fix.
