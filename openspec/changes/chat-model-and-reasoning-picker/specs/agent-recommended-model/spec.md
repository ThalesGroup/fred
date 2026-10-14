## Purpose

Lets the editor of an agent instance recommend the chat model its conversations
start on, replaces the team per-template overrides, and retires the per-agent
reasoning settings.

## ADDED Requirements

### Requirement: An agent instance can recommend a chat model

An agent instance SHALL carry an optional recommended chat profile. When set, it
SHALL be the starting model for that instance's conversations and SHALL take
precedence over the team default. When unset, the instance SHALL follow the team
default, including later changes to it.

#### Scenario: Following the team picks up a new default

- **GIVEN** an instance with no recommendation
- **WHEN** a team editor changes the team default to D
- **THEN** the instance's new conversations start on D

### Requirement: The agent form shows and edits the recommendation

The agent create/edit form SHALL show a "Recommended model" choice in its
General section. The choice SHALL list the models allowed by the platform and
enabled by the team on the instance's pod. Its first option SHALL be "Team default
model", with a helper line naming today's default and saying it follows the
team admin's changes; saving it SHALL store no recommendation. Every enabled
model SHALL also be listed on its own, today's default included, and picking
one SHALL pin it. A stored recommendation that is no longer selectable SHALL be
shown flagged as unavailable.

#### Scenario: Editor picks another model

- **WHEN** the editor selects model A and saves
- **THEN** A is stored as the instance's recommendation

#### Scenario: Editor follows the team

- **WHEN** the editor saves with "Default model" selected
- **THEN** no recommendation is stored

### Requirement: A recommendation is validated when it is written

Create and update SHALL reject a recommendation that names any of the
following, with a validation error:
- a model not allowed by the platform for the team;
- a model disabled by the team;
- a profile the instance's pod does not serve as chat.

An update that omits the field SHALL leave it unchanged. An explicit null SHALL
clear it. The check against the team's disabled models SHALL run again inside
the agent's write transaction, and an update that omits the field SHALL keep
the stored value, never the one loaded before the write.

#### Scenario: Recommending a team-disabled model

- **WHEN** an update names a profile of a model the team disabled
- **THEN** it is rejected and the stored recommendation is unchanged

#### Scenario: A disable lands while the agent form is open

- **GIVEN** the agent form loaded agent X recommending model B
- **WHEN** a team admin disables B, then the editor saves a prompt change to X
- **THEN** X's recommendation stays cleared and the prompt change is saved

### Requirement: Team per-template overrides become instance recommendations

The team routing policy SHALL no longer hold per-template overrides. On upgrade,
each stored override SHALL be copied as the recommendation of every instance of
that team created from that template that has no recommendation. The override
SHALL then be dropped. Importing a bundle that carries per-template overrides
SHALL apply the same mapping to the bundle's instances and report how many were
mapped.

#### Scenario: Upgrade with an override

- **GIVEN** a team override mapping template T to profile P, an instance I1 of T
  with no recommendation, and an instance I2 of T recommending Q
- **WHEN** the upgrade migration runs
- **THEN** I1 recommends P, I2 still recommends Q, and the policy has no overrides

#### Scenario: Importing an old bundle

- **WHEN** a bundle whose routing policy carries overrides is imported
- **THEN** the matching imported instances without a recommendation receive it,
  and the import report counts them

### Requirement: Per-agent reasoning settings are retired

Agent templates, agent instances, the agent form and the agent APIs SHALL no
longer expose a per-agent reasoning offer or reasoning default. Stored instances
and import bundles carrying those settings SHALL still load, with the settings
ignored. For one SDK minor, an agent definition that still sets them SHALL load,
log one deprecation warning per definition class, and behave as if they were
unset. The composer's reasoning control SHALL be emitted whenever at least one
model has its reasoning enabled platform-wide.

#### Scenario: Importing an export with the former reasoning settings

- **WHEN** a bundle whose agent tuning carries the former reasoning settings is imported
- **THEN** the agents are created and the settings are ignored

#### Scenario: Reasoning control without an agent opt-in

- **GIVEN** a platform admin enabled reasoning on one model
- **WHEN** execution is prepared for any agent instance
- **THEN** a reasoning control is emitted
