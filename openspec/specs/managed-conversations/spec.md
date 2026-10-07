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

A conversation whose managed agent has been deleted SHALL preserve its recorded agent display name, strike through only that name in the chat header and sidebar, provide an accessible deleted/read-only description with a tooltip on hover and keyboard focus. Its composer SHALL remain visible and disabled with a localized read-only placeholder, without a separate deletion banner. It SHALL prevent messages, commands, retries, human-input responses/skips, execution continuation/restart, attachment additions/removals and execution-context changes. Its historical human-input prompts and interrupted-execution records SHALL remain readable without executable actions. Starting a fresh conversation with that deleted instance SHALL be unavailable. Existing title management, reading/downloading attachments and conversation deletion SHALL retain their current permissions.

#### Scenario: Preserve a renamed agent after deletion and reload

- **GIVEN** an agent renamed after its conversation was created
- **WHEN** the agent is deleted and the user reloads the conversation list and conversation
- **THEN** the latest name remains visible with strikethrough in the sidebar and conversation header
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

Conversations whose agents still exist SHALL retain their existing message submission, commands, human-input interactions, execution recovery and navigation behavior. History caching and stale-response protection SHALL remain effective. A session freshly bound during its first send SHALL NOT lose its optimistic messages while its metadata or history becomes available.

#### Scenario: A new first turn and a live conversation

- **WHEN** the user creates a conversation and sends its first message, or opens another live-agent conversation
- **THEN** its existing send and history behavior remains usable without wiping the first optimistic turn
- **AND** deletion of a different agent does not put this conversation into read-only mode
