# Fred model routing

Fred's first production routing contract is intentionally small: it selects
the chat model used by an agent. It does not route by prompt, operation,
planning phase, or an inferred business purpose.

This page is the operational guide for platform administrators, team editors,
users, and developers of agentic pods. The frozen API details remain in
`CONTROL-PLANE-PRODUCT-CONTRACT.md` §37 and §40 and
`RUNTIME-EXECUTION-CONTRACT.md` §8.32 and §8.55.

## V1 scope

- `chat` is the only active agent-routing capability.
- A platform administrator may impose one chat model on all managed agents.
- A team editor may select a team chat default and override it per agent.
- A pod operator supplies the local chat profiles, local default, and optional
  per-agent overrides in `models_catalog.yaml`.
- Ordinary users do not select a model per message.
- There are no `operation`, `purpose`, `planning`, or `routing` rules.

`ModelCapability` remains an extensible technical type. `embedding` is retained
because a future document processor may need a distinct embedding-model policy.
That policy will be designed with its real consumer and will not reuse the chat
policy implicitly. `language` is a legacy SDK value; first-party catalogs do not
publish language profiles.

## The three configuration levels

### Platform binding

An organization administrator can configure one authoritative chat binding:

```text
provider + model name + strictly validated settings
```

It applies to every managed agent turn, including HITL resume and nested managed
agent invocation. It is resolved over the trusted runtime-to-control-plane
channel on every turn. It is not accepted from a browser request or from
`RuntimeContext`.

The settings schema has no credential, header, cookie, or generic passthrough
field and rejects unknown keys. It does not inspect whether a value placed in an
allowed string field is itself secret; operators must never put credentials in
those values.

The binding may name a model absent from pod catalogs. This is deliberate: the
platform operator is the deployment-wide authority on the model that is
reachable and licensed. A platform binding therefore bypasses team model
enablement. Direct execution by raw `agent_id` remains pod-local in V1.

### Pod policy

Each agentic pod owns a `models_catalog.yaml`. It declares:

- reusable chat profiles;
- one local chat default;
- optional static `agent_id -> profile_id` overrides.
- optionally, one or more named OpenAI-compatible discovery sources for chat profiles.

The pod catalog is the fallback and the local source of model construction
settings. It does not contain team, user, operation, or purpose rules.

### Team policy

A team editor can choose:

- `chat_default_profile_id`, used by managed agents without a more specific
  choice;
- `agent_profile_overrides`, a flat `agent_id -> profile_id` map.

A team policy is a preference among models already enabled for that team. It
never grants access to a model. Team administrators and analysts may read the
policy; only a team editor may change it. Personal-space owners already have the
team-editor authority required for their personal team.

## Deterministic precedence

For a managed chat turn, Fred selects the first applicable value:

```text
platform chat binding
  > pod static agent override
  > team per-agent override
  > team chat default
  > pod chat default
```

The platform binding is absolute. Without it, a pod static override is the
operator's local escape hatch. Team per-agent selection then wins over the team
default. No scoring or rule ordering is involved.

To override the pod default platform-wide in either static or discovery mode,
open **Capabilities > Models > Platform chat model** and select a chat model
from the Catalog or Discovery section of the selector. The selector carries its validated
provider, wire ID and inference settings. Models with unsupported or ambiguous
settings are not offered there; the advanced manual form can set a supported
binding directly. For Mistral via the OpenAI-compatible client, use `openai`,
the Mistral model ID, and `{"base_url": "https://api.mistral.ai/v1"}` in that
form. This binding takes precedence over
the pod and team defaults. The Models table's `default_on` switch controls
team access to a model; it does not select the chat default. Remove the platform
binding to restore team and pod routing. A discovery-only deployment with no
binding opens a single-action dialog every time a platform administrator enters
the Models view after every pod has reported that it has no manual chat default. This
also applies when manual models exist but none was declared as default. The dialog explains that selecting a
platform model overrides team choices and opens the binding editor; it cannot
be postponed. Only a platform administrator can write or delete that binding,
since advanced settings can change the destination for a provider credential.

The same panel has a separate **Fallback chat model**. It is used only when a
saved choice names a discovered model confirmed absent by a successful refresh.
It does not override a valid choice or the forced platform binding. Select a
manual chat profile from the catalog; the picker offers profiles common to the
available agent pods, and the pod resolves its current connection settings
when needed. A manual declaration is an operator choice, not a health check.
Without a usable fallback, that turn fails explicitly. A discovery outage
does not trigger this fallback.

The four profile-valued levels have **one** implementation,
`fred_sdk.contracts.context.resolve_effective_chat_profile`, shared by the pod
runtime (which resolves it per turn to build the chat client) and the control
plane (which resolves it to tell the composer which model the next turn will
use). The platform binding sits above all four and is handled by each caller,
because it names a concrete `(provider, name)` rather than a profile.

## What the composer shows

The chat composer names the model the next turn will actually route to, resolved
for that team and that agent instance through the precedence above. It is not a
picker — the choice belongs to the team policy and the platform binding.

Two things it deliberately does:

- It shows the model even when the agent offers no reasoning toggle. Model
  identity and reasoning are independent; conflating them is what made the
  composer previously display the single reasoning-enabled model regardless of
  routing.
- It flags a model that is not enabled for the team. That turn will fail before
  the LLM call, and saying so beats an opaque error later.

It shows nothing when nothing resolves, such as an unreachable pod or a pod
declaring no chat default with no team policy. For a confirmed removed
discovered choice, it shows the configured platform fallback.

## Platform administration

The Models view represents a concrete model by `(provider, name)`, or by
`(provider, model_id)` where a profile declares one (see the pod author guide
below). If several profiles use the same concrete model, enabling it is still
one administrative decision. Profile settings and profile ids remain pod-owned.

For team policy, the control plane offers only profiles explicitly advertised
as chat profiles. It never infers capability from a profile-id prefix.

An administrator can edit a model's display name in the Models view after the
model is advertised. The saved name is stored by model capability id and takes
effect in the admin list and chat model picker without restarting a pod. It
takes priority over a name supplied by the gateway or a static profile; clearing
it restores that name, or the model identifier when no name was supplied. The
display name does not change the inference id, routing identity or team grants.

With several enabled agentic pods, the two catalog views intentionally differ:

- The platform model inventory is the union of models advertised by reachable
  pods. This lets an administrator see and enable a model served somewhere.
- The team chat picker is the intersection of chat profile ids advertised by
  every enabled model-capable pod, and each id must map to the same concrete
  `(provider, name)` everywhere. A saved team preference must have the same
  meaning regardless of which pod serves the turn.

If an enabled pod is unreachable while that intersection is computed, the
picker and write validation fail closed. They do not certify a profile using an
incomplete deployment view.

## Agentic pod author guide

### Discover chat models from a gateway

An operator can add several discovery sources alongside manually listed chat profiles:

```yaml
version: v1
discovery:
  - source_id: primary-gateway
    base_url: https://gateway.example/v1
    include_model_ids: [chat-small, chat-large]
  - source_id: secondary-gateway
    base_url: https://other-gateway.example/v1
    include_model_ids: [other-chat]
default_profile_by_capability:
  chat: chat.manual.safe
```

`discovery` is optional and always contains a nonempty list, including when
there is only one endpoint. Source IDs must be unique. Existing catalogs
without `discovery` retain their behavior. The chat default stays in
`default_profile_by_capability` and references a manually declared profile.

At pod startup and on administrator refresh, Fred sends an authenticated
`GET https://gateway.example/v1/models` and reads the OpenAI-compatible JSON
shape `{"data": [{"id": "chat-small"}]}`. The administrator can edit the
`/models` URL of each source in **Capabilities > Models**; each YAML URL remains
its reset value. A successful refresh updates that source's inventory
immediately while preserving the other sources' models.
`base_url` is also used for chat inference. Set `OPENAI_API_KEY` in the pod
environment; never put the key in YAML. Sources on one pod share this key, so
use separate pods when endpoints need different credentials. `source_id` is a stable operator-chosen
identity. Changing it creates new model capability and profile ids, which need
new admin grants. `include_model_ids` is optional; its listed IDs must be
present during initial catalog validation. A later administrator refresh can
confirm a listed model's removal and apply the platform fallback.

The standard OpenAI `/models` response does not identify chat models, context
sizes, or supported reasoning levels. Configure a gateway that lists chat
models only, or use the allowlist to exclude embeddings and other modalities.
OpenAI's `GET /models/{id}` also returns only basic model metadata; its model
documentation publishes context limits, but the list API does not supply them
for automatic discovery. The admin view leaves unknown limits blank.
When an entry supplies `capabilities.completion_chat`, only `true` entries are
discovered; entries without this field remain eligible. Fred shows the exact
upstream `id` in the admin Models table and uses it for inference. A nonblank
`name` or `display_name` may provide a label. Positive integer
`context_length`, `max_model_len`, or Mistral's `max_context_length`, `max_input_tokens`, and
`max_output_tokens` are shown when present. These optional values are
informational; they do not change routing, grants, or reasoning controls.
Reasoning effort levels are available only when declared in manual catalog
profiles; `/models` does not provide a portable list of supported levels.
An administrator can open a model's detail icon to request `GET /models/{id}`
from the same source on demand. The returned fields are shown as a key/value
tree. OpenAI's detail response still has no context field; Mistral's response
may include `max_context_length`, already shown in the model row when supplied
by its list response.

Opening **Capabilities > Models** refreshes the discovered inventory before
listing models. Pill tabs separate manually declared profiles from models
advertised by discovery, using the pod's inventory provenance rather than the
model name. Both tabs offer the same activation, team controls, and text filter.
The model identity names every pod that advertises it. The Discovery tab has a
compact refresh button; its details reveal URL settings and unavailable models. If a
pod advertises discovered models but control-plane lacks registered state for
that source, the view names it as unavailable for URL management.
New models are highlighted and start without a team grant.
Removed models remain visible as unavailable in the discovery summary, while
static profiles continue to appear in the manual section. A failed
refresh preserves the last verified inventory and displays an error. If the
YAML endpoint is unavailable at startup, the pod starts with its static
profiles; the first managed turn can apply a saved administrator URL. Until a
discovery URL responds successfully, a discovery-only pod has no chat model
for direct pod-local turns. A catalog without `discovery` makes no network
call.

### Static profiles

A minimal catalog is:

```yaml
version: v1

common_model_settings:
  max_retries: 0
  temperature: 0.0

default_profile_by_capability:
  chat: chat.mistral.small

profiles:
  - profile_id: chat.mistral.small
    capability: chat
    model_display_name: Mistral Small
    model:
      provider: openai
      name: mistral-small-latest
      settings:
        base_url: https://api.mistral.ai/v1

  - profile_id: chat.mistral.medium
    capability: chat
    model_display_name: Mistral Medium
    model:
      provider: openai
      name: mistral-medium-latest
      settings:
        base_url: https://api.mistral.ai/v1

agent_profile_overrides:
  my.expensive.agent: chat.mistral.medium
```

Some OpenAI-compatible gateways serve each model on its own `base_url` but
expect the same `model` value for all of them. Declare `model_id` on those
profiles: it replaces `name` in the model's identity (its capability id), while
`name` stays what is sent to the provider. Without it the profiles below are one
model, sharing a label, a reasoning toggle and a team enablement decision.

```yaml
profiles:
  - profile_id: chat.gw.mistral-small
    capability: chat
    model_id: mistral-small
    model_display_name: Mistral Small 4
    model:
      provider: openai
      name: mistral
      settings:
        base_url: https://gateway.example/small/v1

  - profile_id: chat.gw.mistral-medium
    capability: chat
    model_id: mistral-medium
    model_display_name: Mistral Medium 3.1
    model:
      provider: openai
      name: mistral
      settings:
        base_url: https://gateway.example/medium/v1
```

Declare `model_display_name` on every profile you give a `model_id`: the
composer labels a model by its display name and falls back to the wire `name`,
which the siblings share, so without it both still read as the same model.

Adopting `model_id` on an existing deployment changes those models' capability
ids, so their team enablement and reasoning toggle must be set again. Give each
model a `model_id` no other profile can reach — one that collides with another
profile's `model_id`, or with a plain `name`, merges them back into one model.

Authoring rules:

1. Treat `profile_id` as an opaque, deployment-global identifier. A readable
   `chat.*` name is useful, but Fred never derives behavior from that prefix.
2. Every profile referenced by the local default or a static override must
   exist and declare the matching capability; invalid catalogs fail at pod
   startup.
3. Pods participating in the same deployment must use the same profile id for
   a team-selectable choice. A profile present on only some pods is excluded
   from team policy.
4. Keep secrets in environment variables or provider credential mechanisms,
   not in committed YAML.
5. Do not add duplicate `language` profiles for chat models. They have no V1
   consumer and cannot be selected by a team chat policy.

The pod exposes `/agents/models-catalog`. Each concrete model entry contains all
of its profile ids for platform enablement and an explicit `chat_profile_ids`
subset for chat policy. This preserves the difference between “this deployment
knows this model” and “this profile is valid for chat routing.”

The response also advertises the two precedence levels only this pod knows —
`default_chat_profile_id` and `agent_chat_profile_overrides` (chat entries only).
The control plane needs both to predict the routed model without guessing; a pod
that omits them reads as declaring neither.

## Failure behavior

- A team write naming an unknown, non-chat, not-universally-available, or
  non-enabled profile is rejected before persistence.
- A stored team profile missing from a pod, or declaring a non-chat capability,
  raises a typed drift error unless a successful discovery refresh confirmed
  its removal. A confirmed removal uses the configured platform fallback;
  neither case silently substitutes the pod default.
- A resolved non-platform model that is no longer enabled for the team fails
  closed before the LLM call.
- With no platform binding and no team policy, behavior reduces to the pod's
  static override and chat default.

## Future embeddings

Embeddings are a different technical client (`get_embeddings`, not a chat
model) and a different policy context. A future surface may express, for
example, “document processor X uses embedding profile Y.” When that consumer
is implemented, it must advertise and validate embedding profiles explicitly,
with its own fallback and authorization contract. It must not reinterpret
`chat_default_profile_id` or `agent_profile_overrides`.
