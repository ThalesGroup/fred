## Purpose

Lets a team curate the models the platform allows it: which are enabled for its
members, which one is the default, and whether reasoning starts on for each.

## ADDED Requirements

### Requirement: The team lists every model the platform allows it

The team settings Models section SHALL list every chat model the platform
allows the team (`can_use`), by display name. Each row SHALL show whether the
model is the team default, enabled for the team, and on by default for
reasoning. Only a team admin SHALL be able to change it, including the
disable-impact read. Team editors and analysts SHALL get a read-only view. In a
personal space, the owner SHALL be able to change it.

#### Scenario: Team editor cannot change the team's models

- **WHEN** a team editor who is not a team admin submits a change to the team's
  models, or requests the disable impact
- **THEN** the request is refused as forbidden and nothing changes

#### Scenario: Team admin changes the team's models

- **WHEN** a team admin submits a valid change
- **THEN** it is accepted

#### Scenario: Model allowed by the platform but disabled by the team

- **GIVEN** models A and B allowed by the platform and B disabled by the team
- **WHEN** a team admin opens the Models section
- **THEN** both rows are listed, A enabled and B disabled

### Requirement: Exactly one default model, always enabled

The team SHALL have at most one default model. A "Set as default" action SHALL
make an enabled model the default. The default model's enable switch SHALL be
disabled, and a write that disables the default model SHALL be rejected. A
write that sets a disabled model as default SHALL be rejected.

#### Scenario: Set as default

- **WHEN** the admin uses "Set as default" on enabled model B
- **THEN** B becomes the team default and shows the "Default" badge, and the
  previous default shows a "Set as default" button

#### Scenario: Default cannot be disabled

- **WHEN** a write disables the current default model
- **THEN** it is rejected with a validation error and nothing changes

#### Scenario: A pod catalog is unreachable while disabling

- **GIVEN** no stored team default, or a model newly disabled by the write
- **WHEN** one of the team's pod catalogs cannot be read
- **THEN** the write is refused as temporarily unavailable and nothing changes

### Requirement: Concurrent edits of the team's models are not lost

A write MAY carry the policy version it was built on. When it does and the
stored version differs, the write SHALL be refused as a conflict and nothing
SHALL change; the Models section SHALL then reload the policy and say so. The
section SHALL accept no change while a save or a reload is in flight, and SHALL
show a load error, with no controls, when the policy or the model list cannot
be read.

#### Scenario: Two admins edit the models at once

- **GIVEN** admins A and B both read version 3
- **WHEN** A saves, then B saves a change built on version 3
- **THEN** B's write is refused, B's section reloads version 4 and shows a
  warning, and A's change is kept

### Requirement: New models arrive enabled with reasoning on by default

Team-disabled models and reasoning-off models SHALL be stored as exceptions. A
model the platform newly allows the team SHALL therefore be enabled for the
team. When its reasoning is enabled platform-wide, the team's reasoning default
for it SHALL start ON, with no team action.

#### Scenario: Platform admin allows a new model

- **GIVEN** a team with stored settings
- **WHEN** a platform admin allows model N for the team and enables its reasoning
- **THEN** N is listed enabled for the team with reasoning on by default

### Requirement: Reasoning default is shown only where reasoning can run

The "reasoning on by default" switch SHALL be shown only for a model whose
reasoning a platform admin enabled. It SHALL set the composer's starting
reasoning state for that model in this team. The platform activation SHALL
remain the ceiling: a team default ON SHALL never make a model reason when the
platform activation is off.

#### Scenario: Platform reasoning off

- **WHEN** the platform admin has not enabled reasoning for model A
- **THEN** A's row shows no reasoning switch

### Requirement: Disabling a model shows its impact and applies it atomically

Disabling a model SHALL first show a confirmation dialog. The dialog SHALL list
the team's agents whose recommended model is that model, which will switch to
following the team default. It SHALL also state that members currently using
that model in a conversation are moved to the agent's recommended model on
their next refresh.
The impact SHALL come from one read. Confirming SHALL disable the model and
clear those agents' recommendations in one transaction.

#### Scenario: Disable a model two agents recommend

- **GIVEN** agents X and Y recommend model B, and agent Z follows the team
- **WHEN** the admin disables B
- **THEN** the dialog lists X and Y and the conversation fallback, and on
  confirmation B is disabled and X and Y follow the team default, in one write

#### Scenario: Cancel

- **WHEN** the admin cancels the dialog
- **THEN** nothing is written

### Requirement: A model revoked by the platform falls back without a team dialog

When the platform stops allowing a model for a team, recommendations naming it
SHALL be ignored at turn time and cleared. A team default naming it SHALL be
cleared too, so the pod default takes over and turns keep working; the Models
section SHALL then show the pod default as the default. Members' conversations
on it SHALL fall back to the agent's recommended model. No team confirmation
SHALL be required. This SHALL apply to a team grant removal, a personal-space
scope revoke and a platform-wide switch-off.

#### Scenario: Platform revokes a recommended model

- **GIVEN** agent X recommends model B
- **WHEN** the platform admin revokes B for the team
- **THEN** X's turns run on the team default and X's recommendation is cleared

#### Scenario: Platform revokes the team default

- **GIVEN** the team's stored default is model B
- **WHEN** the platform admin revokes B for the team
- **THEN** the stored default is cleared, turns run on the pod default, and the
  Models section shows the pod default as "Default"
