## ADDED Requirements

### Requirement: Active-turn text appears directly in the conversation

During an active managed ReAct or Deep turn, submitting plain text SHALL create a durable user message at the end of the visible thread. A subtle pending indicator SHALL remain while its provisional rank is fixed and disappear when the agent incorporates it. Commands, attachments, and human-input answers SHALL retain their dedicated paths.

#### Scenario: Submit during a tool call

- **GIVEN** an active turn with a dispatched tool call
- **WHEN** the user submits plain text
- **THEN** the message appears at the bottom of the chat with a pending indicator
- **AND** its provisional rank stays fixed while tool results and trace updates arrive

#### Scenario: Reload before delivery

- **GIVEN** a submitted message has not reached a model boundary
- **WHEN** the browser reloads or the user returns to the conversation
- **THEN** the same message and pending state are restored from history without a duplicate submission

#### Scenario: HTTP acknowledgements arrive out of order

- **GIVEN** two updates are visible with provisional ranks while an agent works
- **WHEN** the second submission's HTTP acknowledgement arrives before the first
- **THEN** neither pending message changes its displayed rank or position
- **AND** each receives its canonical rank only on delivery

### Requirement: In-thread messages reach a safe model boundary

The runtime SHALL give an eligible submitted message to the active ReAct or Deep agent once, after dispatched tool results and before the next model decision. At that boundary it SHALL persist a definitive canonical rank and delivered state. Conversation history SHALL remain ordered by rank, with each tool call/result group intact. Messages missing the boundary SHALL remain pending for the next eligible turn.

#### Scenario: Delivery after tool results

- **GIVEN** a tool batch is running when the user submits a message
- **WHEN** all dispatched results are available and the agent resumes model work
- **THEN** the agent receives the message once after those results
- **AND** its definitive rank places it after the completed tool batch in reloaded history

#### Scenario: End before another model call

- **GIVEN** a submitted message is still pending
- **WHEN** the active turn ends without another model decision
- **THEN** the message remains visible and is submitted as the next ordinary turn

#### Scenario: Human-input pause and another pod

- **GIVEN** a message is submitted during a turn that pauses for human input
- **WHEN** the user answers and another runtime replica resumes the turn
- **THEN** the message remains pending until the resumed agent reaches its next safe model boundary
- **AND** it is incorporated once with the same message identity

#### Scenario: Graph fallback pauses for human input

- **GIVEN** a pending message starts the next ordinary Graph turn
- **WHEN** Graph reaches a human-input pause before a final answer
- **THEN** the message receives its definitive opening rank and no longer appears pending

### Requirement: In-progress updates receive separate assistant replies

The agent SHALL send a visible assistant message responding to an in-progress update before continuing ordinary model or tool work. User delivery and reply persistence SHALL commit atomically before that work resumes. The reply SHALL have its own canonical rank and survive history reload and checkpoint recovery. A progress question SHALL receive current status when the model produces a visible reply. If two completed reply calls produce no usable answer, the agent SHALL send an explicit, localized failure notice through the same delivery path. A failed model call or persistence SHALL leave the user message pending.

#### Scenario: Progress question during a tool call

- **GIVEN** the agent has dispatched a tool call
- **WHEN** the user asks for progress and the tool results arrive
- **THEN** the agent sends a separate assistant status message before any further tool calls
- **AND** the chat keeps that message separate from the later final answer after reload

#### Scenario: Reply failure before delivery

- **GIVEN** a steered user message is waiting at a model boundary
- **WHEN** the reply model call fails or the reply cannot be persisted
- **THEN** the message remains pending with its clock and can be retried

#### Scenario: Reply has no visible text

- **GIVEN** a steered user message is waiting at a model boundary
- **WHEN** the model returns only reasoning, no assistant message, or an unexpected tool call on two attempts
- **THEN** the agent sends a visible failure notice in the conversation language through the normal reply and delivery path
- **AND** the original task continues without losing or duplicating the user message

#### Scenario: Checkpoint recovery after reply persistence

- **GIVEN** the assistant reply was persisted before the graph checkpoint committed
- **WHEN** the same exchange resumes on another replica
- **THEN** the user update and assistant reply are injected once in rank order without another reply
- **AND** the reply's model usage contributes once to the resumed turn total without a second history badge

### Requirement: In-thread submission survives concurrency and failure

The runtime SHALL authorize the session and managed agent before storing a submitted message. Message identity SHALL make retries idempotent across runtime replicas. Concurrent submissions and history writes SHALL not overwrite or duplicate messages or canonical ranks. A runtime crash SHALL leave an unincorporated message visible and eligible for a later continuation or ordinary turn. Deleting a conversation SHALL delete its submitted messages with the rest of its history.

#### Scenario: Duplicate HTTP submission

- **WHEN** the same authorized message identity is submitted twice to different replicas
- **THEN** only one user message exists in history and at most one incorporation occurs

#### Scenario: Failed or interrupted stream

- **GIVEN** a submitted message is not durably incorporated
- **WHEN** the executing replica stops or its stream is interrupted
- **THEN** the message remains visible and pending after reload
- **AND** the next eligible continuation can incorporate it

#### Scenario: Unauthorized submission

- **WHEN** a caller submits text to another user's session or an unauthorized agent
- **THEN** the runtime refuses the request and stores no message

## MODIFIED Requirements

### Requirement: Background conversation states are visually distinct

The sidebar SHALL distinguish running turns, pending user input and completed unread answers known to the current browser tab, retaining waiting and unread indicators across refresh in that tab. Pending input SHALL use a readable localized noninteractive chip. Completed unread answers SHALL use a plain blue dot without shadow, cleared on opening. Errors, cancellation and premature EOF SHALL NOT imply that an answer is ready.

#### Scenario: Running generation

- **WHEN** a conversation has a running turn
- **THEN** its sidebar row displays animated thinking dots
- **AND** it does not display a completed-answer dot

#### Scenario: User reply is required

- **WHEN** a live-agent conversation pauses for user input or an execution decision
- **THEN** its row displays the localized waiting chip below its metadata
- **AND** opening the conversation preserves that chip until the next turn or deletion
- **AND** read-only deleted-agent rows do not solicit a reply

#### Scenario: Reload while user input is pending

- **WHEN** reloading the open conversation and its existing history load reconstructs a pending HITL request (or an unanswered request from a legacy runtime without availability annotations)
- **THEN** its waiting chip is restored without extra requests
- **AND** history loading does not overwrite a running turn's status

#### Scenario: Completed background answer

- **WHEN** a detached turn receives its final answer and ends normally
- **THEN** its sidebar row displays one plain blue unread dot without shadow
- **AND** opening the conversation clears that dot

#### Scenario: Incomplete background turn

- **WHEN** a detached turn fails, is cancelled or ends before a terminal event
- **THEN** it does not display a completed-answer dot or send an answer-ready notification

#### Scenario: Refresh restores known indicators

- **WHEN** the page reloads in the same tab after a known pending-input pause or completed unread answer
- **THEN** the sidebar restores the waiting chip or unread dot without extra requests or notifications
- **AND** opening clears unread, history reconciles waiting, a new turn clears waiting, and Stop or deletion clears both
- **AND** running turns are not restored; pending in-thread user messages are restored from history

#### Scenario: Local indicator storage is unavailable

- **WHEN** local indicator data is malformed or browser storage cannot be read or written
- **THEN** indicator behavior remains functional in memory without crashing the chat
- **AND** stored indicator ids are bounded to the latest 100 per indicator

#### Scenario: Background pause while on an administration page

- **GIVEN** a turn continues in the current browser tab after the user leaves its conversation
- **WHEN** it pauses for human input while an administration page is open
- **THEN** a single localized waiting-for-reply notification appears
- **AND** its action opens the originating team, agent and conversation

## REMOVED Requirements

### Requirement: Plain text can wait while a managed agent works

**Reason**: In-thread submission supersedes the browser-only pending queue and its edit/remove/send controls.

**Migration**: Existing unsent browser-only drafts and unconsumed server-side mailbox entries are discarded during upgrade. Messages already delivered and persisted in conversation history remain. New submissions use the chat composer and appear in the thread.

### Requirement: A pending message can steer the active turn

**Reason**: Delivery is requested by ordinary composer submission, without a secondary queue action.

**Migration**: Use in-thread submission and its pending/delivered indicator.

### Requirement: Steering works across runtime replicas

**Reason**: Cross-replica behavior is covered by durable in-thread submission and safe-boundary delivery.

**Migration**: Message identity and history state replace the steering mailbox lease and turn-specific offer.

### Requirement: Prototype limits are explicit

**Reason**: The queue and its unavailable-delivery state no longer exist.

**Migration**: ReAct and Deep accept active-turn plain text directly; Graph and non-text actions retain existing turn controls.

### Requirement: Abandoned steering ownership is reclaimed

**Reason**: The separate steering mailbox and its expiration cleanup are removed.

**Migration**: Pending messages remain in conversation history until incorporated, deleted with the conversation, or handled by the next ordinary turn.
