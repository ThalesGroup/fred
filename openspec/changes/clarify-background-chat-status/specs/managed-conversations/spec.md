## ADDED Requirements

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

- **WHEN** reloading the open conversation and its existing history load reconstructs an unanswered HITL request
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
