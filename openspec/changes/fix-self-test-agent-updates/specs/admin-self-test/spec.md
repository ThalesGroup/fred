## ADDED Requirements

### Requirement: The harness agent stays editable

An agent instance of a self-test harness template SHALL be updatable by an editor of its team without a template access grant, because such templates are never admitted to the capability catalog. Instances of every other template SHALL still be refused an update once their team cannot use the template.

#### Scenario: Disable and re-enable the harness agent

- **GIVEN** a harness agent instance in a team holding no grant on the harness template
- **WHEN** an editor disables it and then enables it
- **THEN** both updates succeed and the instance status follows them

#### Scenario: Tune the harness agent's system prompt

- **GIVEN** a harness agent instance in a team holding no grant on the harness template
- **WHEN** an editor updates its system prompt
- **THEN** the update succeeds and the new prompt is stored

#### Scenario: Ordinary template access revoked

- **GIVEN** an instance of an ordinary template whose team can no longer use that template
- **WHEN** an editor updates it
- **THEN** the update is refused with 403 and the instance is unchanged
