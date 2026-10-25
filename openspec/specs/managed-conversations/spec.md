# Managed conversations Specification

## Purpose

Keeps managed conversations accessible independently of their agent's lifetime and makes their execution availability explicit without moving message history out of the runtime.

## Requirements

### Requirement: History survives deletion of the managed agent

Deleting a managed agent SHALL preserve its existing conversation metadata and runtime message history. A conversation SHALL remain discoverable and readable through its original session identity when its owning runtime can be resolved and reached. History access SHALL NOT require execution preparation or a live agent instance, and SHALL NOT substitute a different agent or runtime.

#### Scenario: Reload an existing conversation after agent deletion

- **GIVEN** an owned managed conversation with persisted messages and a recorded runtime
- **WHEN** its agent is deleted and the user opens the conversation after a browser reload
- **THEN** the conversation remains listed and displays its persisted messages and traces from the recorded runtime
- **AND** the conversation keeps its original session identity

#### Scenario: Cached history remains scoped to its conversation

- **GIVEN** a deleted-agent conversation with cached messages and a second conversation
- **WHEN** the user switches between them while history requests are pending
- **THEN** each conversation displays only its own messages and a late response does not replace the other conversation's thread

### Requirement: Deleted-agent conversations are read-only for execution

A conversation whose managed agent has been deleted SHALL preserve its recorded agent display name, append a localized deletion suffix to that name in the chat header and sidebar (including grouped headers), and provide an accessible deleted/read-only description with a tooltip on hover and keyboard focus. The suffix SHALL be "(deleted)" in English and "(supprimé)" in French, remain visible when a long name is truncated, and replace strikethrough. The sidebar title, metadata and grouped agent label SHALL use 70% opacity without dimming the selection background or actions. Its composer SHALL remain visible and disabled with a localized read-only placeholder, without a separate deletion banner. It SHALL prevent messages, commands, retries, human-input responses/skips, execution continuation/restart, attachment additions/removals and execution-context changes. Its historical human-input prompts and interrupted-execution records SHALL remain readable without executable actions. Starting a fresh conversation with that deleted instance SHALL be unavailable. Existing title management, reading/downloading attachments and conversation deletion SHALL retain their current permissions.

#### Scenario: Preserve a renamed agent after deletion and reload

- **GIVEN** an agent renamed after its conversation was created
- **WHEN** the agent is deleted and the user reloads the conversation list and conversation
- **THEN** the latest name remains visible with the localized deletion suffix and no strikethrough in the sidebar and conversation header
- **AND** the sidebar text uses 70% opacity even when the conversation is neither selected nor hovered
- **AND** the conversation title remains readable and the composer is visibly disabled
- **AND** hovering or focusing the entry explains that the agent was deleted and the conversation is read-only

#### Scenario: Creation races agent deletion

- **WHEN** conversation creation races its managed agent's deletion
- **THEN** a committed conversation retains consistent agent metadata and the latest name after deletion
- **OR** creation is refused without inserting an orphan row

#### Scenario: Legacy conversation without a recoverable agent name

- **GIVEN** a conversation whose agent was deleted before name snapshots were introduced
- **WHEN** the conversation opens
- **THEN** a localized generic agent label carries the same deleted and read-only indications
- **AND** history still loads through the recorded runtime when available

#### Scenario: Submit through the composer or a command

- **GIVEN** a conversation confirmed to reference a deleted agent
- **WHEN** the user reaches the composer, a command, keyboard submission or a retry action
- **THEN** the composer remains visibly disabled and no execution request or new optimistic user message is produced
- **AND** no new conversation is started with that instance

#### Scenario: Pending human input or execution recovery

- **GIVEN** history containing unanswered human-input prompts or an interrupted execution for a deleted agent
- **WHEN** the conversation loads
- **THEN** the historical prompt or interruption remains readable
- **AND** answering, skipping, approving, continuing and restarting cannot execute the agent

#### Scenario: Consult attachments and manage the conversation

- **GIVEN** a deleted-agent conversation with existing attachments
- **WHEN** its owner consults the conversation
- **THEN** existing attachments remain readable and downloadable under their existing access controls
- **AND** attachment uploads, removals and execution-context edits are unavailable
- **AND** existing title management and conversation deletion remain available under their existing permissions

### Requirement: Agent deletion is distinct from unresolved availability

An agent-deleted state SHALL come from an authoritative lookup of the session's managed instance within its team. Loading, failed catalog requests, disabled/suspended instances and unavailable runtimes SHALL NOT be interpreted as agent deletion. A saved conversation whose execution availability has not yet been established SHALL withhold execution controls until that state is known. History resolution or fetch failures SHALL have an explicit unavailable-history state instead of being presented as successful empty history.

#### Scenario: Runtime is offline but the agent still exists

- **GIVEN** an existing managed agent whose runtime cannot be reached
- **WHEN** its conversation opens
- **THEN** the UI reports unavailable history without claiming the agent was deleted
- **AND** it does not change the session's stored agent identity

#### Scenario: Historical runtime cannot be recovered

- **GIVEN** an older conversation with no recorded runtime and no surviving agent instance
- **WHEN** the conversation opens
- **THEN** the UI marks the agent as deleted and explains that history is unavailable
- **AND** it does not guess a runtime or imply that the conversation has no messages

#### Scenario: Availability is pending or a request fails

- **WHEN** an owned saved conversation has no confirmed availability result or its availability request fails
- **THEN** the UI does not claim agent deletion or offer executable chat actions until availability is established
- **AND** any already loaded history remains readable

#### Scenario: Deletion while the conversation is open

- **GIVEN** an open conversation whose agent is deleted through the frontend
- **WHEN** the deletion succeeds and the conversation's availability is refreshed
- **THEN** the conversation switches to read-only while retaining its history
- **AND** a subsequent execution attempt refused because the instance disappeared preserves the draft and does not append a successful-looking user turn

### Requirement: History access preserves service and authorization boundaries

The existing session-detail API SHALL provide history-routing and agent-deletion metadata only after validating the authenticated user's team access and session ownership. Returned runtime URLs SHALL be browser-safe ingress URLs without internal service addresses. The browser SHALL read message content directly from the runtime, which SHALL retain its authenticated-owner filter. Execution preparation and managed runtime resolution SHALL continue to reject deleted instances.

#### Scenario: Another user's session or a different team

- **WHEN** an authenticated user requests history-routing details for a session owned by another user or belonging to a different team
- **THEN** the request is refused without returning the session details or history URL

#### Scenario: Authorized read independent of execution

- **GIVEN** an owned conversation whose agent has been deleted and whose runtime is resolvable
- **WHEN** its owner reads the session details and message history
- **THEN** the details contain a browser-safe history URL and the runtime returns only that owner's messages
- **AND** Control Plane does not proxy message content and execution preparation still refuses the deleted instance

### Requirement: Live-agent conversation behavior remains compatible

Conversations whose agents still exist SHALL retain their existing message submission, commands, human-input interactions, execution recovery and navigation behavior. History caching and stale-response protection SHALL remain effective. A session freshly bound during its first send SHALL retain its initial submission across intermediate renders before the router binding commits, SHALL start exactly one turn after successful session creation without a second submission, and SHALL NOT lose its optimistic messages while its metadata or history becomes available. Navigating away SHALL invalidate the local handoff exemption; a later unresolved visit SHALL remain protected.

#### Scenario: A new first turn and a live conversation

- **WHEN** the user creates a conversation and sends its first message, or opens another live-agent conversation
- **THEN** its existing send and history behavior remains usable without wiping the first optimistic turn
- **AND** deletion of a different agent does not put this conversation into read-only mode

#### Scenario: Router binding commits after an intermediate render

- **GIVEN** a first submission creates a session while router binding is deferred and session details are still loading
- **WHEN** an intermediate render occurs before that binding commits
- **THEN** the original submission starts once after successful creation without another Enter or button click
- **AND** a refused creation preserves the draft and cannot start a turn

#### Scenario: Leave while the first creation is pending

- **GIVEN** the initial submission is awaiting session creation
- **WHEN** the user navigates to another session, starts another new conversation or leaves the chat page
- **THEN** the pending submission does not start a runtime turn or clear the next conversation's state
- **AND** returning to its original session does not revive the revoked submission

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
