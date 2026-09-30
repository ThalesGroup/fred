## Purpose

Lets a person approve the tools shown in a human approval prompt for the rest of one managed conversation while preserving each tool call's runtime approval pause and authorized resume.

## ADDED Requirements

### Requirement: A person can remember approval for displayed tools

A managed tool-approval prompt SHALL offer Accept, Reject, and Approve for this conversation as neutral, vertically stacked actions. Approve for this conversation SHALL approve the pending call and remember only the gated tool names displayed in that prompt. It SHALL NOT apply to agent-question prompts.

#### Scenario: Remember one tool

- **GIVEN** a pending approval for tool A
- **WHEN** the person selects Approve for this conversation
- **THEN** the pending call resumes with the normal approval decision and tool A is remembered for that conversation

#### Scenario: Reject does not remember

- **WHEN** the person rejects a pending approval
- **THEN** the call is rejected and no tool is remembered

### Requirement: Remembered approval is scoped to one conversation

The managed client SHALL retain a remembered grant across page reloads and browser restarts for the same signed-in user, agent instance, and conversation. Another user, agent instance, or conversation SHALL NOT inherit it. A missing or invalid stored grant SHALL NOT cause automatic approval.

#### Scenario: Return to the same conversation

- **GIVEN** the person has remembered approval for tool A
- **WHEN** that person reopens the same agent conversation
- **THEN** the grant is available for later calls to tool A

#### Scenario: Different conversation

- **GIVEN** tool A is remembered in one conversation
- **WHEN** the same agent calls tool A in another conversation
- **THEN** a human approval prompt remains necessary

### Requirement: Later matching pauses resume automatically

The managed client SHALL automatically resume a later tool-approval pause with the existing approved decision only when every gated tool name in that pause is remembered for the current conversation. The runtime SHALL still create and validate each pause and resume. Failed automatic resumes SHALL restore a manually answerable prompt without repeated automatic retries.

#### Scenario: Same tool called again

- **GIVEN** tool A is remembered for a conversation
- **WHEN** a later call to tool A raises an approval pause
- **THEN** the client resumes it automatically and the person is not asked again

#### Scenario: Mixed batch

- **GIVEN** tool A is remembered but tool B is not
- **WHEN** one approval prompt gates both tools
- **THEN** the prompt remains visible and requires a human decision

#### Scenario: Resume cannot reach the runtime

- **WHEN** an automatic resume fails before the runtime accepts it
- **THEN** the pending prompt is restored and the client does not retry it automatically in a loop
