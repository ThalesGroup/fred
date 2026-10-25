## ADDED Requirements

### Requirement: Plain text can wait while a managed agent works

During an active managed ReAct or Deep turn, the composer SHALL accept additional plain-text messages into a conversation-scoped ordered list. The list SHALL appear in a compact disclosure panel above the composer, with each message on one ellipsized line. Each waiting message SHALL be editable or removable through a menu with icons until immediate delivery is requested. A message awaiting immediate delivery SHALL remain visible but locked until its outcome is known. The list SHALL submit its next message as an ordinary turn only after the active turn ends and the conversation is available for another user turn.

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

### Requirement: A pending message can steer the active turn

The user SHALL be able to request immediate delivery of a pending plain-text message using Fred's shared secondary tonal button labeled `Send` or `Envoyer`. For an active ReAct or Deep turn, the runtime SHALL make it available before the next model decision after the already dispatched tool batch completes. It MUST NOT split an outstanding assistant tool-call/result group. A message that has not reached that boundary before the turn ends SHALL remain available as the next ordinary turn. The interface SHALL distinguish pending from actually delivered messages.

#### Scenario: Delivery after tools

- **GIVEN** a ReAct or Deep turn with tools running and an eligible pending message
- **WHEN** the tools complete and the agent is about to call the model again
- **THEN** the model sees the new user message once after the tool results and before it decides its next action
- **AND** the conversation shows and persists the message in that order

#### Scenario: No further decision boundary

- **GIVEN** a pending message marked for immediate delivery
- **WHEN** the active turn ends before another model decision
- **THEN** the message remains pending and is eligible for the next ordinary turn

#### Scenario: Human confirmation between offer and delivery

- **GIVEN** an immediate message was accepted during an active turn
- **WHEN** the agent pauses for tool confirmation before reaching another model boundary
- **THEN** the message remains undelivered during the pause
- **AND** the matching resumed turn consumes it once after the tool results and before its next model decision

#### Scenario: Unauthorized steering

- **WHEN** a caller tries to steer a session they do not own or an agent they cannot use
- **THEN** the runtime refuses the request without making the message visible to the active agent

### Requirement: Steering works across runtime replicas

An active ReAct or Deep turn SHALL accept a steering request handled by another runtime replica. The runtime SHALL use a turn identity to reject stale requests for a later turn of the same session. A matching HITL resume on another replica SHALL retain an accepted but undelivered message. A stale or absent active turn SHALL refuse immediate delivery without claiming the message was delivered.

#### Scenario: Cross-replica steering and HITL resume

- **GIVEN** a turn running on replica A and an authenticated steering request handled by replica B
- **WHEN** the turn reaches its next model boundary, including after a HITL resume handled by replica B
- **THEN** the agent sees the message once and the client receives a delivery event

#### Scenario: Stale turn request

- **GIVEN** a request carrying the identity of an earlier turn
- **WHEN** another turn is now active in the same session
- **THEN** the runtime rejects the request without injecting it into the later turn

### Requirement: Prototype limits are explicit

The first implementation SHALL offer immediate steering only for plain-text messages in active ReAct and Deep turns. Graph turns MAY use the ordinary pending queue but SHALL NOT receive immediate steering. Commands, attachments and human-input answers SHALL NOT be queued or steered during an active turn. If immediate steering is unavailable, the message SHALL stay pending rather than appear delivered.

#### Scenario: Unsupported active execution

- **GIVEN** an active Graph turn or an expired active turn
- **WHEN** the user requests immediate delivery
- **THEN** the interface keeps the message pending and identifies that delivery did not occur
