## Purpose

Lets a capability work on the files a user attaches in the chat - keeping the
bytes it needs, since the platform keeps none - while the user's removal of a
file reaches the capability's copy too.

## ADDED Requirements

### Requirement: Active capabilities receive attached files

When a user attaches a file in a chat session, the chat SHALL hand the file to
every capability active in that session that declares an attachment handler,
with the capability id, its base URL, the team id and the session id. It SHALL
do so in parallel with the platform's own ingestion and before the attachment
is marked ready, so a message sent once the attachment is ready finds the
capability's copy.

#### Scenario: A Word file attached in a session with the capability active

- **WHEN** a user attaches a Word file in a session where a capability with a handler is active
- **THEN** the handler receives the file and the session's context
- **AND** the attachment turns ready only after the handler has answered

#### Scenario: A capability that is not active

- **WHEN** the session's agent does not use a capability
- **THEN** that capability's handler is not called

### Requirement: A handler never fails the attachment

A handler's rejection SHALL be logged and SHALL NOT fail, delay beyond the
handler's own answer, or alter the platform's handling of the attachment.

#### Scenario: The capability's upload fails

- **WHEN** a handler rejects
- **THEN** the attachment is ingested and shown as usual

### Requirement: Removing a file reaches the capability's copy

A handler MAY return a forget callback. The chat SHALL call it when the user
removes that attachment from the chat, including when the removal happens
before the handler has answered (the callback is then called as soon as it is
returned). A forget callback's rejection SHALL be logged and SHALL NOT block
the removal.

#### Scenario: A file attached then removed before sending

- **WHEN** the user removes an attachment whose handler returned a forget callback
- **THEN** the forget callback is called once

#### Scenario: Removed before the capability answered

- **WHEN** the user removes an attachment while its handler is still running
- **THEN** the forget callback is called once the handler returns it

### Requirement: An asset slot can take several files

A capability config widget SHALL be able to stage several files for one asset
slot. The agent save SHALL send them as repeated slot entries, in order, so the
capability receives one ordered list per slot. A single-file slot SHALL behave
as before.

#### Scenario: Staging three templates for a library slot

- **WHEN** an author stages three files for one asset slot and saves the agent
- **THEN** the capability receives the three files, in the staged order, for that slot
