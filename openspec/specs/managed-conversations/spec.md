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

The agent SHALL send a concise, user-facing assistant message responding to an in-progress update before continuing ordinary model or tool work. User delivery and reply persistence SHALL commit atomically before that work resumes. The reply SHALL have its own canonical rank and survive history reload and checkpoint recovery. A progress question SHALL receive current status when the model produces a visible reply. Continuation SHALL retain that reply and direct the agent to complete any part of the update it did not fully answer, with tools available, unless the update stops the task. If two completed reply calls produce no usable answer, the agent SHALL send an explicit, localized failure notice through the same delivery path. A failed model call or persistence SHALL leave the user message pending.

#### Scenario: Progress question during a tool call

- **GIVEN** the agent has dispatched a tool call
- **WHEN** the user asks for progress and the tool results arrive
- **THEN** the agent sends a separate assistant status message before any further tool calls
- **AND** the chat keeps that message separate from the later final answer after reload

#### Scenario: Update needs more work than the immediate reply

- **GIVEN** an update asks a substantive question requiring more tool work
- **WHEN** the immediate reply explains the current progress
- **THEN** the next model decision retains that reply and the unanswered update in context
- **AND** the agent is directed to complete the remaining request with tools available

#### Scenario: Reply failure before delivery

- **GIVEN** a steered user message is waiting at a model boundary
- **WHEN** the reply model call fails or the reply cannot be persisted
- **THEN** the message remains pending with its clock and can be retried

#### Scenario: Reply has no visible text

- **GIVEN** a steered user message is waiting at a model boundary
- **WHEN** the model returns only reasoning, no assistant message, or an unexpected tool call on two attempts
- **THEN** the agent sends a visible failure notice in the conversation language through the normal reply and delivery path
- **AND** the original task continues without losing or duplicating the user message

#### Scenario: Reply is tool data or the completed task

- **GIVEN** a steered user message is waiting at a model boundary
- **WHEN** the reply model emits tool arguments as a JSON object or a long answer to the original task
- **THEN** the runtime retries instead of displaying that output as the interim assistant reply
- **AND** the original task continues after a usable reply or the localized failure notice

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

### Requirement: Historical HITL actions reflect runtime availability

For unanswered human-input requests in the trailing exchange, a supporting runtime SHALL report current response availability from authoritative shared execution state after enforcing session ownership. Managed chat SHALL offer response controls only for requests reported pending. An unavailable request SHALL remain readable with a localized noninteractive notice and SHALL NOT remain labelled as awaiting a response or as an indefinitely running question. This state SHALL NOT fabricate a failed tool result, a successful response, or a completed continuation. Unknown availability SHALL preserve readable history, withhold response controls, and offer a lookup retry. Older runtime responses omitting availability SHALL retain legacy compatibility.

#### Scenario: Consumed response absent from history

- **GIVEN** history contains a question without a response but its runtime pause is no longer pending
- **WHEN** the user reloads the conversation
- **THEN** the question is shown as unavailable with no choice, submit or skip action
- **AND** no execution or history repair is performed

#### Scenario: Already-started resume

- **GIVEN** a question still appears in history and its resume has a blocking shared claim
- **WHEN** another browser or runtime replica loads that conversation
- **THEN** the interface does not offer a duplicate answer
- **AND** it does not claim that the continuation failed or completed

#### Scenario: Genuinely pending question

- **GIVEN** the latest runtime state still awaits that exact occurrence with no blocking claim
- **WHEN** the user reloads
- **THEN** the question remains answerable with its original identity and choices

#### Scenario: Distinct sibling occurrences

- **GIVEN** two historical questions have distinct occurrence identities and only one remains pending
- **WHEN** the conversation loads
- **THEN** only the pending question has answer controls
- **AND** the other question's state does not hide or answer its sibling

#### Scenario: Availability lookup fails

- **WHEN** the runtime cannot establish availability because storage or identity decoding is unavailable
- **THEN** the question is shown with an explicit unknown state and a retry action
- **AND** the UI does not label it obsolete or failed, erase its history, or submit an answer

#### Scenario: Answer races the availability snapshot

- **GIVEN** a question was reported pending and another request consumes it
- **WHEN** a subsequent answer receives an authoritative stale-occurrence rejection
- **THEN** managed chat refreshes availability for the same conversation and removes unusable response controls
- **AND** it does not automatically replay the answer or affect another conversation

#### Scenario: Unauthorized history read

- **WHEN** a caller requests another user's conversation
- **THEN** no checkpoint or claim availability information is disclosed

#### Scenario: Reload does not resume execution

- **WHEN** a conversation with an unavailable question is reloaded
- **THEN** displaying its status does not restart a model call, execute a tool, release a claim, or keep an interrupted stream alive
