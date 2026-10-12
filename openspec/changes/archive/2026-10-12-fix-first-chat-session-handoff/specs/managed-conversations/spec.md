## MODIFIED Requirements

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
