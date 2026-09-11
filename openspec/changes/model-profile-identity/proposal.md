## Why

GitHub issue [#2629](https://github.com/ThalesGroup/fred/issues/2629) (reported as
PRISM-78): a team whose default chat model is Mistral Medium still sees "Mistral
Small 4" in the composer, with a reasoning toggle that does nothing.

Some OpenAI-compatible gateways serve each model on its own `base_url` but expect
the same `model` value for all of them. A model's identity is its capability id,
`model__{provider}__{name}`, so two such profiles become one model: they share a
display name, one reasoning toggle and one `can_use` decision. Routing itself is
correct — the turn is built from the resolved profile — which is what makes the
mismatch confusing rather than merely wrong.

It cannot be fixed in configuration: `model.name` is also the `model` value sent
to the provider, and gateways validate it.

## What Changes

- `ModelProfile.model_id` (optional, `models_catalog.yaml`): an explicit model
  identity that replaces `model.name` in the capability id. `model.name` stays the
  wire value. Absent means unchanged behaviour; blank is rejected at pod boot.
- `ModelProfile.capability_id` becomes the one derivation of that id, and the pod's
  `/agents/models-catalog` projection groups and ids entries by it.
- `ModelSelection.capability_id` carries the winning profile's identity, so
  `RoutedChatModelFactory.build_for_chat` gates team enablement and the reasoning
  toggle on it instead of re-deriving from `model.name`. A platform binding has no
  profile and keeps `model_capability_id(provider, name)`.

No control-plane, OpenAPI or frontend change: the composer's effective-chat-model
read already selects the catalog entry that owns the winning profile. The shipped
`apps/fred-agents/config/models_catalog.yaml` does not adopt the field.

## Capabilities

### New Capabilities

- `model-routing`: how a chat turn's model is identified — the identity behind the
  capability id, and the gates that consume it.

### Modified Capabilities

None.

## Impact

- Runtime: `model_routing/contracts.py`, `model_routing/resolver.py`,
  `model_routing/provider.py`, `app/agent_app.py`.
- Tests: catalog projection, `build_for_chat` enablement and reasoning gating,
  contract validation, and one control-plane test pinning the composer-label
  resolution.
- Docs: `RUNTIME-EXECUTION-CONTRACT.md` §8.78, `LLM_ROUTING_FRED.md` author guide.
- **Upgrade note:** a deployment that adopts `model_id` gets new capability ids for
  those models, so team enablement and the reasoning toggle must be set again for
  them.
