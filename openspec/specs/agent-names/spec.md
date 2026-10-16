# agent-names Specification

## Purpose
Keep every agent of a team or personal space identifiable by its name, by refusing or resolving name conflicts wherever an agent is created, renamed, duplicated, copied or imported.

## Requirements

### Requirement: An agent name is unique within its team

Two agents of the same team or personal space SHALL NOT have the same name. Names SHALL be compared after removing surrounding spaces and ignoring case. The same name MAY be used in different teams. The name SHALL be stored without surrounding spaces.

#### Scenario: Same name in the same team
- **WHEN** team A has an agent named "Assistant RH"
- **AND** a user creates an agent named " assistant rh " in team A
- **THEN** the creation is refused and no agent is created

#### Scenario: Same name in another team
- **WHEN** team A has an agent named "Assistant RH"
- **AND** a user creates an agent named "Assistant RH" in team B
- **THEN** the agent is created in team B

#### Scenario: Personal space
- **WHEN** a user's personal space has an agent named "Notes"
- **AND** the user creates another agent named "Notes" in their personal space
- **THEN** the creation is refused

#### Scenario: Surrounding spaces removed
- **WHEN** a user creates an agent named "  Analyst  " in a team with no agent of that name
- **THEN** the agent is created with the name "Analyst"

#### Scenario: Name freed by deletion
- **WHEN** the agent "Analyst" of team A is deleted
- **AND** a user creates an agent named "Analyst" in team A
- **THEN** the agent is created

### Requirement: Conflicts on create, rename and duplicate are refused clearly

Creating, renaming or duplicating an agent under a name already taken in its team SHALL be refused with a conflict response carrying a stable code that identifies a name conflict. The agent form and the duplicate dialog SHALL warn about a taken name on the name field as soon as the person leaves that field, before any submit, and SHALL keep the submit action unavailable while the conflict lasts. A conflict only the server detects (a name taken in the meantime) SHALL be shown on the same field, keeping what the user entered. Renaming an agent to its own name with a different case or spacing SHALL be accepted.

#### Scenario: Warned on leaving the field
- **WHEN** team A has an agent "Analyst"
- **AND** in the creation form a user types "analyst" in the name field and moves to another field
- **THEN** the name field shows that the name is already used in the team, and the create action is unavailable until the name changes

#### Scenario: Name taken in the meantime
- **WHEN** another user creates "Analyst" in team A after the form checked the name
- **AND** the user submits the form with "Analyst"
- **THEN** the server refuses it and the name field shows the conflict, with the form values kept

#### Scenario: Rename to a taken name
- **WHEN** team A has agents "Analyst" and "Writer"
- **AND** a user renames "Writer" to "analyst"
- **THEN** the rename is refused, the name field shows that the name is already used in the team, and "Writer" keeps its name

#### Scenario: Change of case on the same agent
- **WHEN** a user renames the agent "analyst" to "Analyst"
- **THEN** the rename is accepted

#### Scenario: Duplicate under a taken name
- **WHEN** a user duplicates "Analyst" in team A and keeps the proposed name "Analyst"
- **THEN** the duplicate is refused and the dialog shows the conflict on the name field

### Requirement: Copies and imports resolve conflicts by renaming

A copy to another team, a marketplace import and a platform import SHALL NOT fail on a name conflict. A copy and a marketplace import SHALL take the first free name of the form `<name> (<word> <n>)`, with n starting at 1, using the comparison of this capability. `<word>` SHALL be `copie` when the request's locale is `fr` and `copy` otherwise; it SHALL come from a fixed server-side map, never from client text. A platform import restores data rather than copying it: it SHALL take the first free `<name> (<n>)`, with n starting at 2.

#### Scenario: Copy with a name differing only by case
- **WHEN** team B has an agent named "analyst"
- **AND** a user whose UI language is French copies the agent "Analyst" of team A to team B
- **THEN** the copy in team B is named "Analyst (copie 1)"

#### Scenario: Import with a conflicting name
- **WHEN** a platform import brings an agent "Analyst" into team A, which already has an agent "Analyst" with another identifier
- **THEN** the imported agent is created as "Analyst (2)"

### Requirement: Existing duplicates are renamed on upgrade

On upgrade, agents of the same team whose names collide SHALL be renamed so that the rule holds. The oldest agent SHALL keep its name; the others SHALL become `<name> (2)`, `<name> (3)` and so on, in creation order, each name staying free in the team and within the name length limit. No agent SHALL be deleted.

#### Scenario: Two agents with the same name
- **WHEN** team A has "Analyst" created on day 1 and "analyst " created on day 2 before the upgrade
- **THEN** after the upgrade they are named "Analyst" and "analyst (2)"
