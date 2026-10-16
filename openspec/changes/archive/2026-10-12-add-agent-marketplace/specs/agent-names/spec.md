## MODIFIED Requirements

### Requirement: Copies and imports resolve conflicts by renaming

A copy to another team, a marketplace import and a platform import SHALL NOT fail on a name conflict. A copy and a marketplace import SHALL take the first free name of the form `<name> (<word> <n>)`, with n starting at 1, using the comparison of this capability. `<word>` SHALL be `copie` when the request's locale is `fr` and `copy` otherwise; it SHALL come from a fixed server-side map, never from client text. A platform import restores data rather than copying it: it SHALL take the first free `<name> (<n>)`, with n starting at 2.

#### Scenario: Copy with a name differing only by case
- **WHEN** team B has an agent named "analyst"
- **AND** a user whose UI language is French copies the agent "Analyst" of team A to team B
- **THEN** the copy in team B is named "Analyst (copie 1)"

#### Scenario: Import with a conflicting name
- **WHEN** a platform import brings an agent "Analyst" into team A, which already has an agent "Analyst" with another identifier
- **THEN** the imported agent is created as "Analyst (2)"
