## MODIFIED Requirements

### Requirement: Plain text can wait while a managed agent works

During an active managed ReAct or Deep turn, the composer SHALL accept additional plain-text messages into a conversation-scoped ordered list. The list SHALL appear in a compact disclosure panel above the composer, with each message on one ellipsized line. Each waiting message SHALL be editable or removable through a menu with icons until immediate delivery is requested. A message awaiting immediate delivery SHALL remain visible but locked until its outcome is known. The list SHALL submit its next message as an ordinary turn only after the active turn ends and the conversation is available for another user turn. The ordinary pending list SHALL live only in the current browser chat visit. Navigation, reload or an interrupted stream SHALL clear it without restoration or automatic replay. Late callbacks SHALL NOT restore a cleared list or modify another visit.

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
- **WHEN** the user changes conversation, leaves the page, reloads or interrupts the stream
- **THEN** the local pending list is cleared and is not restored on return
- **AND** late responses do not requeue those messages or affect a new conversation

## REMOVED Requirements

### Requirement: Pending messages survive navigation and execution failure

**Reason**: The user chose a local visit-scoped queue consistent with unfinished chat generation.
**Migration**: This PR's durable recovery proposal is withdrawn; no durable queue API or new storage format is shipped.

### Requirement: Steering cleanup preserves pending messages

**Reason**: Steering is temporary runtime coordination; abandoned ownership is reclaimed rather than retained for queue recovery.
**Migration**: Reuse the existing temporary mailbox and lease index. No Alembic migration or backfill is required.

## ADDED Requirements

### Requirement: Abandoned steering ownership is reclaimed

The runtime SHALL complete turn cleanup despite request cancellation, stop lease renewal and preserve any replacement turn's ownership. A normal human-input pause SHALL keep its existing resume semantics; an interrupted stream SHALL release its temporary steering messages. Expired steering rows SHALL be reclaimed at startup and every 60 seconds while SQL and a healthy runtime remain available, in bounded batches.

#### Scenario: Cancellation during teardown

- **WHEN** a streamed turn is cancelled while teardown awaits I/O
- **THEN** the heartbeat is stopped and the matching steering ownership is released before cancellation propagates
- **AND** a later turn is preserved

#### Scenario: Runtime crash

- **WHEN** a runtime stops before cleanup and its lease expires
- **THEN** a healthy runtime reclaims the expired row without reopening the conversation
- **AND** a late heartbeat does not revive it
