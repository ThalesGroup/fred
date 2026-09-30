## ADDED Requirements

### Requirement: Retired GitHub selections are cleaned from managed agents

The same control-plane data upgrade that retires document-search SHALL remove
`mcp-web-github-readonly` and its historic `mcp:`-prefixed form from stored
agent capability selections and configuration. It MUST preserve unrelated
agent data and SHALL NOT select a replacement capability or change grants and
suspension state.

#### Scenario: Existing agent selects GitHub
- **WHEN** an agent's explicit selection contains either retired GitHub ID
- **THEN** the upgrade removes those selections while preserving other IDs and their order
- **AND** an agent that selected only GitHub has an explicit empty selection

#### Scenario: Inherited defaults and unrelated settings
- **WHEN** a stored selection is absent, null or empty, or a tuning payload contains other configuration
- **THEN** those states and unrelated settings remain intact while retired GitHub config entries are removed
- **AND** reapplying the migration makes no further data changes

#### Scenario: Invalid persisted tuning
- **WHEN** an agent tuning payload is not a JSON object
- **THEN** it is left unchanged with a diagnostic that does not print its contents
