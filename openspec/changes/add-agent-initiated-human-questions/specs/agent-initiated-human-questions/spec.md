## Purpose

Lets an interactive ReAct or Deep agent ask its user a question during a turn, receive a choice or text answer, and continue that same turn without confusing the question with tool approval.

## ADDED Requirements

### Requirement: An interactive agent can ask one question through a platform tool

The platform SHALL offer one `ask_user` tool to an interactive ReAct or Deep agent when the conversation enables agent questions. The tool SHALL accept a question, zero to four single-choice options, and whether free text is allowed. The agent SHALL select the most relevant options before calling; the runtime SHALL reject more than four rather than truncate them. A question SHALL allow at least one answer form. Its prompt SHALL use the existing human-input contract and carry the raising tool call's occurrence identity.

#### Scenario: Single choice

- **GIVEN** an interactive agent with agent questions enabled
- **WHEN** it asks a question with three options and no free text
- **THEN** the person can select exactly one of those options and the same turn resumes

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
- **THEN** managed chat displays them in their given order, one per centered row

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

#### Scenario: Invalid question form

- **WHEN** the agent calls `ask_user` with neither options nor free text enabled, or with duplicate or empty option identifiers
- **THEN** the call returns a tool error without pausing the conversation

### Requirement: The answer returns to the calling agent

On resume, `ask_user` SHALL return one result to its own tool call that distinguishes the selected option, the entered text, and a skipped question. It SHALL reject an option identifier that the question did not offer. The agent SHALL receive the result in the same turn and be able to continue reasoning or use other tools.

#### Scenario: Agent uses a choice and comment

- **WHEN** a person selects an offered option and supplies a comment
- **THEN** the calling agent receives both values in its tool result and can continue the same turn

#### Scenario: Agent uses text only

- **WHEN** a person answers a text-only question
- **THEN** the calling agent receives the text without a fabricated option identifier

#### Scenario: Mismatched answer

- **WHEN** a resume names an option absent from the pending question
- **THEN** it does not report that option as a valid answer to the agent

### Requirement: A person can skip an agent question

An unanswered `ask_user` prompt SHALL offer a skip action at the bottom right and a close control at the top right that performs the same action. Skipping SHALL resume the calling tool with an explicit unanswered result and a short instruction in the turn language to continue with stated assumptions, record the skipped response in history, and SHALL NOT fabricate a choice, text answer, or a new user turn. A tool-approval prompt SHALL retain its own approval choices and SHALL NOT gain this skip action.

#### Scenario: Skip a poorly posed question

- **WHEN** the person skips a pending agent question
- **THEN** the agent receives an explicit skipped result and can continue the turn, and reloading the conversation does not restore that question as pending

#### Scenario: Close a question

- **WHEN** the person closes a pending agent question with the top-right control
- **THEN** the question is skipped and the agent continues the same turn with the same result as the bottom-right skip action

#### Scenario: Localized skip instruction

- **GIVEN** a turn whose language is French or English
- **WHEN** the person skips the question
- **THEN** the calling agent receives the instruction to continue with explicit assumptions in that language

#### Scenario: Approval remains distinct

- **WHEN** the pending prompt is an approval for a proposed tool call
- **THEN** the person sees the existing approval actions and no agent-question skip action

### Requirement: Conversation control determines availability

Managed chat SHALL expose a platform-owned control for agent questions, initially enabled and stored per conversation. When the control is off, the agent SHALL not see `ask_user` on a new turn. When the interactive control is absent, including noninteractive execution, the agent SHALL not see `ask_user`; absence SHALL remain distinct from an explicit off value in the runtime context. A resume of a question already pending SHALL remain answerable even if the control has since been switched off; the switch takes effect on the next new turn.

#### Scenario: First turn before eager controls load

- **GIVEN** a new managed conversation whose eager preparation has not populated the composer controls
- **WHEN** the first turn's preparation offers the agent-question control
- **THEN** the runtime context follows the conversation's selected value or the enabled default

#### Scenario: Disable for a conversation

- **WHEN** a person switches agent questions off before sending the next message
- **THEN** the next agent turn does not offer `ask_user`

#### Scenario: Noninteractive execution

- **WHEN** an agent runs without an interactive chat control
- **THEN** `ask_user` is absent and the agent cannot create a new human wait through that tool

#### Scenario: Existing pause survives a control change

- **GIVEN** an agent question is already pending
- **WHEN** the person switches future questions off and answers the pending one
- **THEN** the answer resumes that question without re-enabling the tool for the next new turn

### Requirement: Multiple questions remain individually answerable

Several `ask_user` calls in one turn SHALL each retain a distinct occurrence identity, and each answer SHALL return to its own call. History and reload SHALL preserve answered questions and restore the unanswered one.

#### Scenario: Sibling questions

- **GIVEN** two agent questions from one turn share a runtime interrupt identifier
- **WHEN** the first is answered
- **THEN** its result belongs to the first call and the second remains answerable

#### Scenario: Reload during several questions

- **GIVEN** the first question in a turn was answered and a second is pending
- **WHEN** the conversation is reloaded
- **THEN** the second question is restored as the only pending question

### Requirement: Graph choice questions preserve their response contract

The Graph choice helper SHALL accept the enriched human response form without losing the selected option, while existing callers that expect an optional option identifier SHALL continue to behave as before.

#### Scenario: Existing Graph choice caller

- **WHEN** an existing Graph choice step receives an answer carrying an offered option identifier
- **THEN** it returns the same identifier it returned before this change
