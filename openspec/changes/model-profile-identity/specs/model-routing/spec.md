## Purpose

Defines how a routable model is identified, separately from the `model` value sent
to the provider, and which decisions that identity governs.

## ADDED Requirements

### Requirement: A profile MAY declare a model identity distinct from its wire name

A `models_catalog.yaml` profile SHALL support an optional `model_id`. When present
it replaces `model.name` in the model's capability id; `model.name` SHALL remain the
value sent to the provider. When absent the identity SHALL be `model.name`. A
declared but blank `model_id` SHALL be rejected when the catalog is loaded.

#### Scenario: Two gateway models share one wire name

- **GIVEN** two chat profiles with the same `provider` and `model.name`, distinct
  `base_url`s, and distinct `model_id` values
- **WHEN** the pod projects its models catalog
- **THEN** it advertises two entries with distinct capability ids, each carrying its
  own display name and profile ids, and both carrying the shared wire name

#### Scenario: A catalog that declares no model_id is unaffected

- **GIVEN** two chat profiles with the same `provider` and `model.name` and no
  `model_id`
- **WHEN** the pod projects its models catalog
- **THEN** it advertises one entry listing both profiles, as before

#### Scenario: Two model_id spellings that normalize to one id stay one model

- **GIVEN** two chat profiles whose `model_id` values differ only in characters
  the capability id normalizes away
- **WHEN** the pod projects its models catalog
- **THEN** it advertises one entry listing both profiles, never two entries
  carrying the same capability id

#### Scenario: A blank model_id fails at load

- **GIVEN** a profile declaring a whitespace-only `model_id`
- **WHEN** the catalog is loaded
- **THEN** loading fails with an error naming that profile

### Requirement: Enablement and reasoning gates use the resolved profile's identity

A routing decision SHALL carry the identity of the profile that won it, and the chat
model build SHALL gate team enablement (`usable_model_ids`) and the platform
reasoning toggle (`reasoning_enabled_model_ids`) on that identity. A platform
operator binding has no profile and SHALL use `(provider, name)`.

#### Scenario: A sibling's enablement does not authorize this model

- **GIVEN** two gateway profiles distinguished by `model_id`, and a team whose
  usable models contain only the first one's identity
- **WHEN** a turn resolves to the second profile
- **THEN** the build is refused with that profile's own capability id

#### Scenario: A sibling's reasoning toggle does not make this model reason

- **GIVEN** the reasoning toggle is on for the first profile's identity only
- **WHEN** a turn resolves to the second profile
- **THEN** the constructed client sends no reasoning setting, while still sending
  the shared wire `model` value

### Requirement: The composer names the model that will answer

The effective-chat-model read SHALL take its display name, team-enablement flag and
reasoning flag from the catalog entry that owns the winning chat profile.

#### Scenario: Two entries share a wire name

- **GIVEN** a pod advertising two entries with the same `name` and distinct
  capability ids, and a team default naming the second entry's profile
- **WHEN** the composer's effective chat model is resolved
- **THEN** it reports the second entry's display name and capability id, and reports
  reasoning as off even though the first entry's toggle is on
