## MODIFIED Requirements

### Requirement: Name of the copy

The copy SHALL keep the source agent's name when no agent of the destination has that name. On a conflict, the copy SHALL take the first free name of the form `<name> (<word> <n>)`, with n starting at 1; `<word>` SHALL be `copie` for a request with locale `fr` and `copy` for `en` or no locale.

#### Scenario: Free name

- **WHEN** team B has no agent named "Analyst"
- **THEN** the copy in team B is named "Analyst"

#### Scenario: Conflicting name

- **WHEN** team B already has agents named "Analyst" and "Analyst (copy 1)"
- **AND** a user whose UI language is English copies "Analyst" to team B
- **THEN** the copy in team B is named "Analyst (copy 2)"
