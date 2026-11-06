## ADDED Requirements

### Requirement: User messages show their own attachments

The frontend SHALL send the turn's ready attachments as `runtime_context.attachments` (id, name, optional MIME type), excluding earlier session attachments. The runtime SHALL persist them as `metadata.extras.attachments` on the user message. The user turn SHALL render them as read-only chips with a file-type icon and name, live and after reload. A message without the field SHALL render as before.

#### Scenario: Sending a message with attachments

- **GIVEN** two ready attachments in the composer
- **WHEN** the user sends a message
- **THEN** the user turn immediately shows two chips with their names
- **AND** the request carries only those two attachments in `runtime_context.attachments`

#### Scenario: Reloading the conversation

- **GIVEN** a stored user message with `metadata.extras.attachments`
- **WHEN** the conversation is reopened
- **THEN** the user turn shows the same chips

#### Scenario: Message without attachments metadata

- **GIVEN** a user message stored before this change
- **WHEN** the conversation is opened
- **THEN** the user turn renders without chips, as before
