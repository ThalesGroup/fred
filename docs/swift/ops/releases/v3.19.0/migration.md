# Migration guide - v3.19.0

Upgrade from: `code/v3.18.1`
Operational impact: **minor** (minimum version: `3.19.0`).

Review these procedures together in the listed dependency order before deployment. Customer-specific values remain in their private repositories; Fred chart values are the production reference. Configuration files named configuration_prod.yaml are for local development only.

No-operation declarations describe ordinary deployment only. Conditional activation steps still require preparation. Validate combined upgrade and rollback in staging before production.

## Preserve vLLM reasoning and make native Mistral replay opt-in

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.19.0/docs/swift/ops/migrations/3702-mistral-thinking-replay.md)

### Applicability

Agent pods using OpenAI-compatible Mistral or vLLM chat endpoints.

### Prerequisites

Native Mistral replay requires an endpoint that accepts `thinking` content blocks
in assistant history.

### Configuration

`replay_mistral_thinking` belongs at the profile level in `models_catalog.yaml`
alongside `supports_thinking`. It defaults to `false`. Leave it omitted or set it
to `false` for the affected vLLM routes, including C3 Small and Medium. Set it to
`true` on custom profiles that previously depended on native replay and whose
endpoint accepts it. The bundled direct Mistral API profiles already opt in.
For discovered profiles, set the option on the discovery source. The bundled
direct Mistral discovery source already opts in. Changing a source URL through
discovery disables replay on the new endpoint.

### Upgrade

Roll out the updated agent pods normally. Update any custom catalog entries
that need to retain native replay before restarting their pods. Existing
conversation rows and checkpoints require no migration.

### Validation

Enable reasoning, send a message, and confirm that the reasoning appears live
and after a reload. Send a follow-up in the same conversation and confirm it
succeeds. For an opt-in endpoint, confirm that the next request carries a native
`thinking` block when the prior reply contained reasoning.

### Rollback

Revert the agent pod image and remove `replay_mistral_thinking` from any custom
catalog applied to the older image. The older behavior can trigger the original
400 again on the affected gateways.

### Limitations

The option enables native Mistral replay. vLLM `reasoning` and
`reasoning_content` are accepted on responses only.

## Count cumulative streaming LLM usage once

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.19.0/docs/swift/ops/migrations/3718-cumulative-streaming-usage.md)

New streaming turns use corrected token counts after a normal deployment; existing data needs no migration.

See the source note for applicability, validation and rollback.

## Use underscore names for Fred built-in tools

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.19.0/docs/swift/ops/migrations/canonical-fred-tool-names.md)

Existing dotted built-in declarations, SDK calls and Graph approval policies remain supported.

See the source note for applicability, validation and rollback.

## Format personal token charts with compact values

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.19.0/docs/swift/ops/migrations/personal-token-chart-formatting.md)

Existing token data and APIs are unchanged; the display update takes effect with normal deployment.

See the source note for applicability, validation and rollback.

## Prepare Fred v3.19.0 release inputs and dependency locks

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.19.0/docs/swift/ops/migrations/prepare-v3-19-0-release.md)

The release preparation itself changes no deployed data or behavior; normal deployment suffices for these inputs.

See the source note for applicability, validation and rollback.

## Retire repository specification tooling

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.19.0/docs/swift/ops/migrations/retire-specification-tooling.md)

The application, data, API, and chart behavior of existing deployments is unchanged.

See the source note for applicability, validation and rollback.

## Open agent creation directly when one template is available

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.19.0/docs/swift/ops/migrations/single-agent-template-creation.md)

Existing agent data and APIs are unchanged; the new flow takes effect with a normal frontend deployment.

See the source note for applicability, validation and rollback.

## Recover malformed tool names in Mistral conversations

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.19.0/docs/swift/ops/migrations/tool-call-name-recovery.md)

Conversation history is adapted when building the model request, so existing checkpoints need no rewrite.

See the source note for applicability, validation and rollback.
