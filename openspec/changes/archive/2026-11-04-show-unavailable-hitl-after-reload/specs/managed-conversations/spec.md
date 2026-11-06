## ADDED Requirements

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
- **AND** running turns and pending-message queues are not restored

#### Scenario: Local indicator storage is unavailable

- **WHEN** local indicator data is malformed or browser storage cannot be read or written
- **THEN** indicator behavior remains functional in memory without crashing the chat
- **AND** stored indicator ids are bounded to the latest 100 per indicator

#### Scenario: Background pause while on an administration page

- **GIVEN** a turn continues in the current browser tab after the user leaves its conversation
- **WHEN** it pauses for human input while an administration page is open
- **THEN** a single localized waiting-for-reply notification appears
- **AND** its action opens the originating team, agent and conversation
