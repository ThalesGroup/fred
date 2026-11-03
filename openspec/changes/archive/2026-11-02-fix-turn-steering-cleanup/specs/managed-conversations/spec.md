## ADDED Requirements

### Requirement: Pending messages survive navigation and execution failure

The runtime SHALL durably retain accepted ordinary queued messages and immediate steering messages, including their identity, order, text and delivery status. The queue SHALL be bounded to 32 messages per conversation and apply the configured chat text limit. Navigation, page reload, turn completion and lease expiration SHALL NOT erase undelivered or uncertain messages. Only explicit user removal, confirmed durable delivery or conversation erasure SHALL remove them. Restoring a queue SHALL require explicit user action before executing it.

#### Scenario: Leave and reopen a conversation

- **GIVEN** accepted messages waiting in an owned conversation
- **WHEN** the user changes conversation or reloads and later returns
- **THEN** the messages reappear in their existing order and status
- **AND** restoration alone does not dispatch a turn

#### Scenario: Concurrent queue actions

- **WHEN** two tabs or runtime replicas try to dispatch the same queued message
- **THEN** only one acquires it for execution
- **AND** a repeated enqueue with the same message identity does not add another copy

#### Scenario: Crash after handing a message to execution

- **GIVEN** a queued message has been handed to execution
- **WHEN** a crash occurs before its delivery is durably recorded
- **THEN** its text remains available with uncertain delivery
- **AND** it is not automatically dispatched again

#### Scenario: Queue persistence fails

- **WHEN** an enqueue cannot be durably saved
- **THEN** the interface retains the unsaved input and reports failure without claiming it was queued

### Requirement: Steering cleanup preserves pending messages

When a managed streaming turn terminates, the runtime SHALL stop lease renewal and complete turn-specific cleanup despite request cancellation. Cleanup SHALL preserve replacement turn ownership, pending messages and uncertain delivery. The runtime SHALL reclaim expired empty steering rows at startup and with a periodic sweep every 60 seconds while SQL and a runtime remain available. Active leases SHALL remain 90 seconds and human-input pauses SHALL retain turn ownership for 30 days; those durations SHALL NOT determine message retention.

#### Scenario: Browser disconnect cancels an active turn

- **GIVEN** an active managed turn with steering state
- **WHEN** the transport detects a disconnected browser and cancels the stream, including while teardown is awaiting I/O
- **THEN** the runtime stops lease renewal and releases that turn's ownership before propagating cancellation, provided SQL is available
- **AND** undelivered and uncertain messages remain recoverable

#### Scenario: A pod crashes before teardown

- **GIVEN** a turn whose runtime pod stops without cleanup
- **WHEN** its active lease expires and another healthy runtime reaches its next periodic sweep
- **THEN** an expired empty row is physically removed without opening the conversation again
- **AND** an expired nonempty row retains its messages for recovery
- **AND** unexpired active turns and human-input pauses remain intact

#### Scenario: A replacement turn starts before old cleanup completes

- **GIVEN** a later turn or matching human-input resume has acquired steering ownership for the same conversation
- **WHEN** the earlier stream finishes teardown
- **THEN** the later turn's steering state and pending messages remain intact

#### Scenario: Disconnect after a human-input pause

- **GIVEN** a turn has paused for human input with an accepted undelivered steering message
- **WHEN** its stream disconnects and a matching resume reaches another replica before paused retention expires
- **THEN** the pending message remains available to that resumed turn

#### Scenario: Human-input pause expires

- **GIVEN** a paused turn still has undelivered messages
- **WHEN** its paused ownership expires
- **THEN** those messages remain visible and recoverable without replaying uncertain delivery automatically
