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

## Platform administration

The Models view represents a concrete model by `(provider, name)`. If several
profiles use the same concrete model, enabling it is still one administrative
decision. Profile settings and profile ids remain pod-owned.

For team policy, the control plane offers only profiles explicitly advertised
as chat profiles. It never infers capability from a profile-id prefix.

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

## Failure behavior

- A team write naming an unknown, non-chat, not-universally-available, or
  non-enabled profile is rejected before persistence.
- A stored team profile missing from a pod, or declaring a non-chat capability,
  raises a typed drift error at runtime. Fred never silently substitutes the
  pod default.
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
