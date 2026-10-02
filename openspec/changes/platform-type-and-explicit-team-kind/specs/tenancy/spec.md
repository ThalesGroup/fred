## Purpose

Defines Fred's tenancy hierarchy (platform → organization → team → project) as
explicit data, so no structural fact is hard-coded or inferred from an identifier.

## ADDED Requirements

### Requirement: Platform authority is its own object
Platform roles, account suspension, platform-level permissions, and the catalog
anchors and class markers of capabilities, applications and Knowledge Base
definitions SHALL be held by a single object of a dedicated `platform` type. No
authorization decision SHALL read them from an `organization` object.

#### Scenario: Platform role checked on the platform object
- **WHEN** Fred checks whether a person holds a platform role or a platform-level permission
- **THEN** the check targets the `platform` object, and the answer is the one the same person received before this change

#### Scenario: Catalog enablement unchanged
- **WHEN** Fred checks whether a team may use a capability, application or Knowledge Base definition that is default-on, explicitly enabled, explicitly disabled, or set by the personal-space class
- **THEN** the answer is the one the same team received before this change

### Requirement: Team kind is explicit data
Every team, personal spaces included, SHALL be a team registry entry with a kind,
`shared` or `personal`, set at creation and never changed. The registry SHALL be
the only authority on a team's kind: no component SHALL derive it from the team
identifier. Components without registry access SHALL receive the kind with the
team they act for.

#### Scenario: Personal space has a registry entry
- **WHEN** a person uses their personal space for the first time
- **THEN** the registry holds an entry for it with kind `personal`, owned by that person

#### Scenario: Team payload carries its kind
- **WHEN** a client lists or reads teams
- **THEN** each team carries its `kind`

#### Scenario: Identifier no longer decides
- **GIVEN** a shared team whose identifier happens to begin with `personal-`
- **WHEN** any component evaluates whether it is a personal space
- **THEN** it is treated as `shared`

### Requirement: Upgrade preserves every existing answer
Upgrading an installation SHALL move platform-level authorization data to the
`platform` object and register every existing personal space, keeping every team
identifier, membership and role. The upgrade SHALL be repeatable without effect
on a second run.

#### Scenario: Existing installation upgrades
- **GIVEN** an installation with platform role holders, enabled capabilities, shared teams and personal spaces
- **WHEN** it upgrades
- **THEN** every person and team receives the same authorization answers as before, and every personal space is registered with kind `personal` under its existing identifier

#### Scenario: Upgrade runs twice
- **WHEN** the upgrade runs on an already-upgraded installation
- **THEN** nothing changes
