---
schema: 1
title: "Preserve vLLM reasoning and make native Mistral replay opt-in"
impact: minor
configuration: production
configuration_reason: "The models catalog adds a per-profile replay_mistral_thinking option, enabled in the bundled direct Mistral API profile."
---

## Applicability

Agent pods using OpenAI-compatible Mistral or vLLM chat endpoints.

## Prerequisites

Native Mistral replay requires an endpoint that accepts `thinking` content blocks
in assistant history.

## Configuration

`replay_mistral_thinking` belongs at the profile level in `models_catalog.yaml`
alongside `supports_thinking`. It defaults to `false`. Leave it omitted or set it
to `false` for the affected vLLM routes, including C3 Small and Medium. Set it to
`true` on custom profiles that previously depended on native replay and whose
endpoint accepts it. The bundled direct Mistral API profiles already opt in.
For discovered profiles, set the option on the discovery source. The bundled
direct Mistral discovery source already opts in. Changing a source URL through
discovery disables replay on the new endpoint.

## Upgrade

Roll out the updated agent pods normally. Update any custom catalog entries
that need to retain native replay before restarting their pods. Existing
conversation rows and checkpoints require no migration.

## Validation

Enable reasoning, send a message, and confirm that the reasoning appears live
and after a reload. Send a follow-up in the same conversation and confirm it
succeeds. For an opt-in endpoint, confirm that the next request carries a native
`thinking` block when the prior reply contained reasoning.

## Rollback

Revert the agent pod image and remove `replay_mistral_thinking` from any custom
catalog applied to the older image. The older behavior can trigger the original
400 again on the affected gateways.

## Limitations

The option enables native Mistral replay. vLLM `reasoning` and
`reasoning_content` are accepted on responses only.
