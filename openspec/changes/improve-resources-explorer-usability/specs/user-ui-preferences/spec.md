# Spec Delta

## ADDED Requirements

### Requirement: Resources file-browser visibility is a personal preference

The Control Plane SHALL save the Resources file browser's open/closed choice in the authenticated person's existing display-preferences record. The choice SHALL default to closed. Only this visibility choice SHALL be database-backed; tree width and expanded branches SHALL retain their existing browser-local or in-memory behavior.

#### Scenario: Save and restore visibility

- **WHEN** a person opens or closes the Resources file browser
- **THEN** a later read for that person, including from another browser, returns the chosen state
- **AND** other saved preferences remain unchanged

#### Scenario: Default without a saved choice

- **WHEN** a person has no preferences record or the preferences read fails
- **THEN** the Resources file browser starts closed without reading an older browser value

#### Scenario: Keep browser-local tree details

- **WHEN** a person resizes the tree or expands a folder branch
- **THEN** no preferences API write is made for those actions

#### Scenario: Keep choices isolated

- **GIVEN** two people use the same browser
- **WHEN** one person changes the file-browser visibility
- **THEN** the other person's stored visibility is unchanged and only their own preference or default is applied at their next sign-in
