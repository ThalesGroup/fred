## MODIFIED Requirements

### Requirement: Plain text can wait while a managed agent works

During an active managed ReAct or Deep turn, the composer SHALL accept additional plain-text messages into a conversation-scoped ordered list. The list SHALL appear in a compact disclosure panel above the composer, with each message on one ellipsized line. Each waiting message SHALL be editable or removable through a menu with icons until immediate delivery is requested. A message awaiting immediate delivery SHALL remain visible but locked until its outcome is known. The list SHALL submit its next message as an ordinary turn only after the active turn ends and the conversation is available for another user turn. The ordinary pending list SHALL live in browser-tab memory per conversation and survive in-app navigation while its turn continues or finishes in the background. Queued ordinary turns SHALL start only while that conversation is open. Stop, deletion, reload, tab close or a genuinely interrupted stream SHALL clear the matching queue without restoration or replay. Delivery acknowledgements SHALL remove consumed steering messages even while detached. Late callbacks SHALL NOT restore a discarded queue or modify another conversation.

#### Scenario: Queue and edit a message

- **GIVEN** an active agent turn
- **WHEN** the user submits a plain-text message and edits it in the pending list
- **THEN** its text returns to the composer for revision and can be queued again without interrupting the active turn

#### Scenario: Drain after completion

- **GIVEN** two plain-text messages waiting in order
- **WHEN** the active agent turn ends without a human-input pause
- **THEN** the first message begins the next ordinary turn, and the second waits for that turn to end

#### Scenario: Pending human input

- **GIVEN** a pending human-input request or interrupted execution that requires a decision
- **WHEN** an agent turn ends
- **THEN** queued ordinary messages remain pending until the human-input path is resolved

#### Scenario: Leave or interrupt the chat

- **GIVEN** messages waiting during an active turn
- **WHEN** the user leaves the conversation within Fred
- **THEN** its queue remains in tab memory and sends no ordinary turn in the background
- **AND** reopening the conversation restores it and resumes FIFO after generation and human-input holds end
- **WHEN** its stream is genuinely interrupted, or the user stops or deletes it, reloads or closes the tab
- **THEN** its queue is discarded without affecting another conversation or allowing late events to restore it

#### Scenario: Delivery while detached

- **GIVEN** a queued message offered to an agent before navigating elsewhere
- **WHEN** the runtime acknowledges delivery while the conversation is detached
- **THEN** that message is absent from the queue on return and is not sent again
