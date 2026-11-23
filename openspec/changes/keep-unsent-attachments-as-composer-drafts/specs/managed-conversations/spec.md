## ADDED Requirements

### Requirement: Unsent attachments are composer drafts of their conversation

An attachment SHALL count as sent once a stored user message lists it in `metadata.extras.attachments`, or when it was created before the latest composer message without an attachment list. New composer turns SHALL record an empty attachment list when no files are sent. Any other attachment of the conversation SHALL be a draft: the composer SHALL show it only in its own conversation, SHALL restore it when the conversation is reopened, and the next message SHALL send it. The attachments drawer, its count and `runtime_context.attachments_markdown` SHALL list only sent attachments and the files of the turn being sent.

#### Scenario: Switching conversation with a draft

- **GIVEN** a file dropped in conversation A without sending a message
- **WHEN** the user opens conversation B with the same agent
- **THEN** B's composer does not show the file
- **AND** a message sent in B does not carry it

#### Scenario: Coming back to a conversation with a draft

- **GIVEN** a file dropped in conversation A without sending a message
- **WHEN** the user leaves A and opens it again
- **THEN** A's composer shows the file and the drawer does not
- **AND** the next message in A sends it, after which the drawer lists it

#### Scenario: Conversation stored before attachment metadata

- **GIVEN** a conversation whose attachments were all created before its latest user message, with no `metadata.extras.attachments`
- **WHEN** the conversation is opened
- **THEN** the drawer lists those attachments and the composer shows none

#### Scenario: Restarting while another draft is waiting

- **GIVEN** an interrupted turn and a new file dropped into its conversation's composer
- **WHEN** the user restarts the interrupted turn
- **THEN** only the interrupted turn's files are sent again
- **AND** the new file stays in the composer after the restart and after reopening the conversation
