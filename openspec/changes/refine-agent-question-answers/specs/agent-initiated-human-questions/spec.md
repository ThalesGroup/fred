## MODIFIED Requirements

### Requirement: An interactive agent can ask one question through a platform tool

The platform SHALL offer one `ask_user` tool to an interactive ReAct or Deep agent, and to Graph steps that invoke it explicitly, when the conversation enables agent questions. The tool SHALL accept a question, an optional short subject title, and zero to four single-choice options. An agent question with two or more choices SHALL also allow free text, regardless of the agent's `allow_free_text` argument; other question forms SHALL follow that argument. The agent SHALL select the most relevant options before calling; the runtime SHALL reject more than four rather than truncate them. A question SHALL allow at least one answer form. Its prompt SHALL use the existing human-input contract and carry the raising tool call's occurrence identity.

#### Scenario: Single choice

- **GIVEN** an interactive agent with agent questions enabled
- **WHEN** it asks a question with one option and no free text
- **THEN** the person can select that option and the same turn resumes

#### Scenario: Multiple choices and free text

- **GIVEN** an interactive agent with agent questions enabled
- **WHEN** it asks a question with two to four options and sets `allow_free_text` to false
- **THEN** the person can select exactly one offered option or submit nonempty text without an option identifier, and the same turn resumes

#### Scenario: Free text

- **GIVEN** an interactive agent with agent questions enabled
- **WHEN** it asks a question with free text and no options
- **THEN** the person can submit nonempty text and the same turn resumes

#### Scenario: Choice with comment

- **GIVEN** an interactive agent with agent questions enabled
- **WHEN** it asks a question with options and free text allowed
- **THEN** the person can submit one option together with an optional comment in a single answer

#### Scenario: Choices in managed chat

- **WHEN** an agent asks a question with multiple choices
- **THEN** managed chat displays them in their given order, one per centered row, followed by a matching text-input row with a fixed gray label "Other" in English or "Autre" in French to the left of the editable area
- **AND** the text-input row submits a text answer without fabricating an option identifier

#### Scenario: Simultaneous questions in one card

- **GIVEN** several `ask_user` calls in one exchange are awaiting answers
- **WHEN** managed chat receives their pauses or reloads their history
- **THEN** it displays one HITL card with a tab for each unanswered question in call order, selecting the first by default
- **AND** each tab has a compact subject label from the question title, or a shortened question when no title exists
- **AND** switching tabs preserves each question’s draft and answering the selected tab resumes its own call
- **AND** answering or skipping a question keeps the card open on the next unanswered tab until no questions remain
- **AND** answered questions remain in the trace while remaining questions stay available

#### Scenario: Question Markdown in managed chat

- **WHEN** an agent question contains Markdown emphasis
- **THEN** managed chat renders the formatted text in the question card instead of showing Markdown markers

#### Scenario: Too many options

- **WHEN** an agent calls `ask_user` with more than four choices
- **THEN** the call fails validation before pausing and no choices are silently removed

#### Scenario: Choice descriptions in managed chat

- **WHEN** a choice has a description
- **THEN** managed chat shows it beneath the label inside the same selectable choice

#### Scenario: Answered question summary in managed chat

- **GIVEN** an agent question has been answered or skipped
- **WHEN** the conversation renders or reloads
- **THEN** a compact card below the matching `ask_user` tool line shows its question and selected choice label, text answer, or skipped state, including an optional comment, without waiting for reload
- **AND** the `ask_user` tool detail drawer lists the offered choices and highlights the selected one when the response is available

#### Scenario: No-LLM Graph test assistant uses the question tool

- **GIVEN** an interactive Graph test assistant with agent questions enabled
- **WHEN** a person runs its confirmation, choice, free-text, or choice-with-comment HITL scenario
- **THEN** the step calls the platform `ask_user` tool without an LLM call and managed chat shows the question and response under the matching tool line
- **AND** disabling the control prevents a new question tool call

#### Scenario: Pending question tool state and text actions

- **WHEN** an `ask_user` call waits for a human answer
- **THEN** its tool line remains in progress until the person answers or skips, without showing an error result for the pause
- **AND** a free-text question shows a compact raised Send button directly left of Skip at the bottom right; tool approvals keep their separate approval actions

#### Scenario: Earlier tool failure followed by an agent question

- **GIVEN** a tool call failed before a later valid `ask_user` call in the same turn
- **WHEN** the valid question pauses for a human answer
- **THEN** the turn emits the pending question without a final answer containing the earlier tool failure

#### Scenario: Tool output before a question pause

- **GIVEN** an agent turn has produced sources, UI parts, or model usage before asking a question
- **WHEN** the question pauses and the person later answers it
- **THEN** the pre-pause metadata remains visible and persisted with the completed exchange, without emitting the earlier tool failure as an answer

#### Scenario: Marked follow-up question after a HITL answer

- **GIVEN** a Mistral assistant response contains the existing typed tool-call marker and a registered `ask_user` name
- **WHEN** its JSON question contains a literal line break inside the quoted string after an earlier question is answered
- **THEN** the runtime validates the public arguments and complete question rules, then routes the call through the ordinary HITL pause, including valid sibling calls, rather than publishing encoded call syntax as the final answer
- **AND** unmarked text, unknown tools, and other malformed argument content remain ineligible for recovery

#### Scenario: Composer waits for an agent question

- **GIVEN** an `ask_user` question is pending or its answer is being submitted
- **WHEN** the person tries to send a new chat message or command in that conversation
- **THEN** the composer and send path block the new turn until the question is answered or skipped and its resume completes
- **AND** another conversation remains usable

#### Scenario: Invalid question form

- **WHEN** the agent calls `ask_user` with neither options nor free text enabled, or with duplicate or empty option identifiers
- **THEN** the call returns a tool error without pausing the conversation
