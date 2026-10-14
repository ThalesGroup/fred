---
schema: 1
title: "Support GPT-6 Astra tools through Azure APIM Responses API"
impact: minor
configuration: none
configuration_reason: "Bundled Fred configuration is unchanged; optional Astra activation requires an operator to update their deployment model catalog."
---
## Applicability

Fred deployments using the Azure APIM chat provider. Existing model profiles keep
their Chat Completions route unless they opt into the Responses API.

## Prerequisites

For optional Astra activation, confirm that the selected APIM product allows
the full `/ai-models/openai/v1/responses` route and authorizes the Astra model
and function tools. Use credentials issued for that product.

## Configuration

No configuration changes are required for a normal upgrade. To activate Astra,
add a chat profile in the deployment model catalog with `provider: azure-apim`,
the authorized Astra deployment name, `use_responses_api: true`,
`reasoning: {effort: low}`, `temperature: null`, and
`azure_apim_resource_path: /ai-models/openai`. Set `azure_apim_base_url` and
the authentication settings for the same APIM product. The bundled
`/genai-aoai-inference/v2` example targets a different gateway route and must
not be reused for this Astra profile. Do not pass Chat Completions
`extra_body.reasoning_effort` to this profile.

## Upgrade

Deploy Fred normally. For optional activation, deploy the updated agent image
before selecting the Astra profile, apply the catalog change, and restart agent
pods if the catalog is mounted through a ConfigMap `subPath`.

## Validation

With synthetic data, run an Astra turn that calls a function tool and another
turn that consumes its result. Verify that an existing APIM profile still uses
Chat Completions.

## Rollback

Select a previously working profile and restore the prior catalog entry. Roll
back the Fred image if needed; no data migration is involved.

## Limitations

Astra is not activated by this change. APIM content guardrail rejections remain
independent of the model endpoint choice.
