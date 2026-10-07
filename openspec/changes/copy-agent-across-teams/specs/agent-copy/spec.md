## Purpose

Copying an agent's configuration to another scope, and duplicating it within its scope, so that an agent built once can be reused without leaking anything owned by its source scope.

A scope is the place an agent lives in and whose items its settings may point to. Today a scope is a team or a personal space; projects and organisations are expected to become scopes too. Every requirement below is stated against the scope so that it holds for them unchanged.

## ADDED Requirements

### Requirement: Who can copy an agent

A user SHALL be able to copy an agent only if they can edit agents in the source team and in each destination team. The personal space SHALL always be a possible destination for its owner. A copy SHALL be refused, for that destination only, when the user cannot edit agents there.

#### Scenario: Editor of both teams

- **WHEN** an editor of team A and team B copies an agent of team A to team B
- **THEN** a new agent exists in team B and every editor of team B can use and configure it

#### Scenario: Not an editor of the destination

- **WHEN** a user who is not an editor of team C requests a copy to team C
- **THEN** the copy to team C is refused and no agent is created in team C

#### Scenario: Personal space

- **WHEN** an editor of team A copies an agent to their personal space
- **THEN** the agent is created in their personal space

### Requirement: Destination readiness is shown before copying

Before copying, the user SHALL see, for each team they can edit and for their personal space, whether the agent can be copied there.
- A destination where the agent template is not enabled SHALL NOT be selectable, and SHALL show "Agent template not enabled".
- A destination that lacks one or more of the agent's capabilities SHALL remain selectable, and SHALL show a warning with the list of missing capabilities.
- When at least one listed destination lacks capabilities, a short explanation SHALL state that the copy will not have every ability while its instructions stay intact.

#### Scenario: Template not enabled

- **WHEN** team B cannot use the agent's template
- **THEN** team B is shown greyed out with "Agent template not enabled" and cannot be selected

#### Scenario: Missing capabilities

- **WHEN** team B cannot use the agent's "web search" capability
- **THEN** team B is selectable, shows a warning, and its tooltip lists "web search"

#### Scenario: Explanation shown

- **WHEN** at least one listed team lacks capabilities
- **THEN** an explanation above the list says the copy will lack those abilities and keep its instructions

### Requirement: What a copy carries

A copy SHALL be a new agent in the destination. It SHALL keep:
- the source agent's template;
- its name, description and instructions;
- its template settings;
- its selected capabilities that the destination can use, each with its settings.

Its **public** settings SHALL be kept as they are. Its **scope-private** settings, those that point to an item owned by the source scope (a library, a folder, a document, a file), SHALL be reset to their default value when the destination is a different scope. The capability SHALL stay enabled.

Capabilities the destination cannot use SHALL be left out of the copy. A capability whose settings the destination rejects SHALL also be left out, and SHALL be reported like a missing capability.

Configuration files of the source agent SHALL NOT be shared between scopes. They SHALL be recreated in the destination scope, as if an editor had uploaded them there.

The copy SHALL NOT carry anything else from the source scope:
- no conversations;
- no agent file space;
- no scope-level model routing or capability settings;
- no references to the source scope's prompts.

#### Scenario: Library selection is dropped

- **WHEN** an agent restricted to two libraries of team A is copied to team B
- **THEN** the copy has document access enabled with no library restriction, and no library of team A is referenced

#### Scenario: Folder selection is dropped

- **WHEN** an agent bound to a specific folder of team A's resources is copied to team B
- **THEN** the copy keeps the resources capability, without a specific folder

#### Scenario: Team wiki follows the destination

- **WHEN** an agent with team wiki access is copied to team B
- **THEN** the copy reads team B's wiki

#### Scenario: Configuration file copied

- **WHEN** an agent whose presentation capability holds a template file is copied to team B
- **THEN** the copy holds its own template file in team B and fills presentations without a new upload

#### Scenario: Configuration file refers to items the destination lacks

- **WHEN** an agent's presentation template uses image folders that team B does not have, and it is copied to team B
- **THEN** the copy keeps the capability and its template, the image fields stay unfilled, and the user is told which folders to create before uploading the template again

#### Scenario: Capability missing in destination

- **WHEN** team B cannot use one of the agent's capabilities and the user copies anyway
- **THEN** the copy is created without that capability and keeps its instructions

### Requirement: Name of the copy

The copy SHALL keep the source agent's name when no agent of the destination has that name. On a conflict, the copy SHALL take the first free name of the form `<name>_imported-<n>`, with n starting at 1.

#### Scenario: Free name

- **WHEN** team B has no agent named "Analyst"
- **THEN** the copy in team B is named "Analyst"

#### Scenario: Conflicting name

- **WHEN** team B already has agents named "Analyst" and "Analyst_imported-1"
- **THEN** the copy in team B is named "Analyst_imported-2"

### Requirement: Copy to several destinations

A copy request SHALL accept several destinations and SHALL report a result per destination: the created agent and the capabilities left out, or the reason for the failure. A failure for one destination SHALL NOT prevent the copy to the others.

#### Scenario: Partial failure

- **WHEN** a user copies an agent to teams B and C and the copy to C fails
- **THEN** the copy to B is created and the result reports the failure for C

### Requirement: Duplicate within a team

Duplicating an agent within its own scope SHALL produce the same result as a copy, under a name chosen by the user. Because the scope does not change, its scope-private settings SHALL be kept, and its configuration files SHALL be recreated for the duplicate.

#### Scenario: Duplicate keeps the template file and libraries

- **WHEN** an editor duplicates an agent with a presentation template and a library restriction in team A
- **THEN** the duplicate in team A has its own template file and the same library restriction

### Requirement: Copies are recorded

Each successful copy or duplicate SHALL record an audit event with the source agent, the source scope, the destination scope, the new agent and the user.

#### Scenario: Audit event

- **WHEN** a copy to team B succeeds
- **THEN** an audit event records the source agent and team, team B, the new agent and the user

### Requirement: Capabilities classify their settings as scope-private or public

Every capability setting SHALL be either scope-private or public, and the classification SHALL be declared by the capability itself, so that a copy can apply it without knowing the capability.
- A setting that points to an item owned by the scope SHALL be declared scope-private.
- A setting that looks like a reference to such an item but is safe to copy SHALL be explicitly declared public.
- Any other setting SHALL be public by default.
- A reference-like setting that is declared neither scope-private nor public SHALL make the automated checks fail.

The classification SHALL be expressed against the scope, not against a particular kind of scope, so that it stays valid when new kinds of scope are introduced.

#### Scenario: Undeclared reference setting

- **WHEN** a capability adds a setting holding identifiers and declares it neither scope-private nor public
- **THEN** the automated checks fail and name the capability and the setting

#### Scenario: Hidden or nested scope-private setting

- **WHEN** a scope-private setting is not shown in the agent form, or sits inside a nested structure such as a slide of a presentation template
- **THEN** a copy to another scope still resets it

#### Scenario: Capability that cannot prepare a copy

- **WHEN** the destination can use a capability but the service hosting it cannot prepare a copy
- **THEN** the copy is created without that capability and reports it as missing
