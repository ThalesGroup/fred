## ADDED Requirements

### Requirement: Organization is an explicit tenant
An organization SHALL be a registry entry with an id and a name. Every team,
personal spaces included, SHALL belong to exactly one organization, set at
creation and never changed. Every person SHALL belong to exactly one
organization.

#### Scenario: Team created in the creator's organization
- **WHEN** an `org_admin` creates a team
- **THEN** the team belongs to that `org_admin`'s organization

#### Scenario: Personal space follows its owner
- **WHEN** a person's personal space is registered
- **THEN** it belongs to that person's organization

### Requirement: Installation organization is configured
The operator SHALL configure the id and name of the installation's organization,
with no default. Every new account SHALL join that organization on its first
authenticated request. Fred SHALL refuse to start when the setting is missing.

#### Scenario: New account joins the configured organization
- **WHEN** a person authenticates for the first time
- **THEN** they are a member of the configured organization

#### Scenario: Setting missing
- **WHEN** Fred starts without the organization setting
- **THEN** it refuses to start and names the missing setting

### Requirement: Organization administration
`org_admin` SHALL govern its organization's teams (create, list, delete, rescue a
team admin) and its `org_admin`s. It SHALL grant no access to team content and
no action on another organization. `platform_admin` SHALL create organizations
and name their first `org_admin`, and SHALL NOT govern teams through its
platform role.

#### Scenario: org_admin creates and lists teams
- **WHEN** an `org_admin` creates a team or lists teams
- **THEN** the action succeeds and the listing contains only teams of their organization

#### Scenario: org_admin reads no team content
- **GIVEN** an `org_admin` with no team role in team T
- **WHEN** they request T's documents, agents, prompts or conversations
- **THEN** access is denied

#### Scenario: Other organization out of reach
- **GIVEN** an `org_admin` of organization A and a team T of organization B
- **WHEN** they read, delete or rescue the admin of T by its id
- **THEN** access is denied

#### Scenario: platform_admin without org role
- **GIVEN** a `platform_admin` who is not `org_admin`
- **WHEN** they create or delete a team
- **THEN** access is denied

### Requirement: Platform team roster for feature management
`feature_manager` SHALL list the teams of every organization, as registry
metadata only.

#### Scenario: feature_manager lists teams
- **WHEN** a `feature_manager` lists teams for capability enablement
- **THEN** teams of every organization are listed, without content access

### Requirement: Upgrade keeps every governance action
Upgrading SHALL create the configured organization, attach every existing team
and person to it, and make every `platform_admin` and `team_manager` holder an
`org_admin` of it. The upgrade SHALL be repeatable without effect on a second
run, and SHALL never reattach a team already attached to an organization.

#### Scenario: Existing installation upgrades
- **GIVEN** an installation upgraded by `platform-type-and-explicit-team-kind`
- **WHEN** it upgrades
- **THEN** every former `platform_admin` and `team_manager` can perform every team governance action they could before

#### Scenario: Upgrade runs twice
- **WHEN** the upgrade runs on an already-upgraded installation
- **THEN** nothing changes

### Requirement: No platform-tier team governance role
No platform role SHALL grant team creation, deletion or admin rescue. The former
`team_manager` role SHALL no longer exist.

#### Scenario: team_manager cannot be granted
- **WHEN** a `platform_admin` grants the `team_manager` role
- **THEN** the request is rejected as an unknown role
