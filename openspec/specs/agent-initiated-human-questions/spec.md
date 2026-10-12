## Purpose

Lets an interactive ReAct or Deep agent ask its user a question during a turn, receive a choice or text answer, and continue that same turn without confusing the question with tool approval.

## Requirements

### Requirement: An interactive agent can ask one question through a platform tool

The platform SHALL offer one `ask_user` tool to an interactive ReAct or Deep agent, and to Graph steps that invoke it explicitly, when the conversation enables agent questions. The tool SHALL accept a question, an optional short subject title, and zero to four single-choice options. An agent question with two or more choices SHALL also allow free text, regardless of the agent's `allow_free_text` argument; other question forms SHALL follow that argument. The agent SHALL select the most relevant options before calling; the runtime SHALL reject more than four rather than truncate them. A question without options SHALL allow free text, regardless of that argument. The tool's description SHALL tell the agent to use it whenever it needs a decision, a preference or a missing detail from the person instead of asking in its reply, to call it once per question when it has several, and never to offer a generic "Other" option. Its prompt SHALL use the existing human-input contract and carry the raising tool call's occurrence identity.

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
- **THEN** managed chat displays them in their given order, one per full-width row with left-aligned text, followed by a matching text-input row that reads as an input field rather than a choice: it shows an edit icon, the localized label "Other" in English or "Autre" in French styled like the choice labels, and a placeholder inviting the person to type, on an input surface, with the typed text in the large body text style and at least the height of a choice
- **AND** the text-input row submits a text answer without fabricating an option identifier

#### Scenario: Compact active question card

- **WHEN** managed chat displays an active agent question
- **THEN** the card uses compact width and spacing and design-system text styles, while keeping choice descriptions, free-text input, and actions readable
- **AND** the card shows no close control

#### Scenario: Simultaneous questions in one card

- **GIVEN** several `ask_user` calls in one exchange are awaiting answers
- **WHEN** managed chat receives their pauses or reloads their history
- **THEN** it displays one HITL card with a tab for each unanswered question in call order, selecting the first by default
- **AND** each tab displays a state icon before its short subject title, or before a localized numbered fallback when no title exists: waiting, answered in the success colour, or skipped, each with an accessible label and the same footprint so the tab width does not change when the state changes; overflowing titles scroll horizontally with the mouse wheel or trackpad without dragging the scrollbar, while vertical page scrolling remains available at the ends
- **AND** selecting a choice records a draft answer and advances to the next question without resuming the agent
- **AND** typed text counts as an answer only once validated, with a small Confirm action or the field's keyboard shortcut, which also advances to the next unanswered question; editing a validated text withdraws it until it is validated again, and picking a choice clears the typed text and replaces it
- **AND** the person can revisit a tab, change its choice or text answer, and skip an individual question
- **AND** a "Skip all" action submits a skip for every pending question, including tabs with drafted answers, in one batch
- **AND** once every tab has a draft answer or skip, one Send action submits all answers together to their own calls
- **AND** skipping one question is offered as the last choice of that question, marked with the Escape key, and the card's action row keeps only "Skip all" and the Send action, which alone uses the primary emphasis
- **AND** the card stays open until the batch is accepted, then removes the submitted tabs even while the resumed stream continues; later questions in that exchange appear without the submitted tabs
- **AND** failed submission preserves editable answers

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
- **AND** a free-text answer to a question with choices appears once as a highlighted localized "Other: <answer>" row in that drawer, even when the agent offered an option named Other
- **AND** the record below the tool line uses the same reply bubble as an answer in the conversation, aligned with the trace steps

#### Scenario: Answer recorded as a user reply in the conversation

- **GIVEN** an agent question has been answered or skipped
- **WHEN** managed chat shows that answer as a reply in the conversation flow, outside the agent trace
- **THEN** the reply sits on the same side as a message the person sends, in a lighter, outlined treatment of the same colour family
- **AND** it recalls the question in a smaller text above the answer, and shows a skipped answer as the localized skipped label

#### Scenario: Tool execution approval response in managed chat

- **GIVEN** a tool execution confirmation is awaiting a person's choice
- **WHEN** the runtime accepts approval, refusal, or skip
- **THEN** managed chat shows the localized user response below the confirmation card without waiting for history reload
- **AND** the response uses the same reply bubble as an answered agent question, recalls which tool or tools the decision concerned, and names the decision
- **AND** the same response remains visible after history reload
- **AND** a resume rejected before acceptance leaves no response in the chat

#### Scenario: No-LLM Graph test assistant uses the question tool

- **GIVEN** an interactive Graph test assistant with agent questions enabled
- **WHEN** a person runs its confirmation, choice, free-text, or choice-with-comment HITL scenario
- **THEN** the step calls the platform `ask_user` tool without an LLM call and managed chat shows the question and response under the matching tool line
- **AND** disabling the control prevents a new question tool call

#### Scenario: Pending question tool state and text actions

- **WHEN** an `ask_user` call waits for a human answer
- **THEN** its tool line remains in progress until the person answers or skips, without showing an error result for the pause
- **AND** a free-text question shows a compact raised Send button at the bottom right with Skip directly to its left; tool approvals keep their separate approval actions

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

#### Scenario: Composer waits for any human-input card

- **GIVEN** a tool approval or a Graph question is pending in the conversation
- **WHEN** the person tries to type or send a new chat message or command there
- **THEN** the composer is held, keeping any draft, until the card is answered, so its number keys reach the card
- **AND** an interrupted-run card, which offers to continue later, leaves the composer usable

#### Scenario: Invalid question form

- **WHEN** the agent calls `ask_user` with a blank question, with duplicate or empty option identifiers, or with more than four options
- **THEN** the call returns a tool error without pausing the conversation

#### Scenario: Question without options

- **GIVEN** an interactive agent with agent questions enabled
- **WHEN** it asks a question with no options and does not enable free text
- **THEN** the question is shown as a free-text question and the conversation pauses for the answer, instead of the call failing

#### Scenario: Tool guidance

- **GIVEN** an interactive ReAct, Deep or Graph agent with agent questions enabled
- **WHEN** the agent receives the `ask_user` tool
- **THEN** both runtimes give it the same description, which asks it to call the tool instead of writing the question in its reply, to call it once per question in the same response when it has several questions, and never to add a generic "Other" option

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

An unanswered `ask_user` prompt SHALL offer a skip action, and SHALL NOT show a separate close control. A single question SHALL offer it in its action row, to the left of any send action; a question grouped with others SHALL offer it as its last choice. When several agent questions are grouped in one card, the card SHALL also offer a "Skip all" action that skips every pending question in one batch. Skipping SHALL resume the calling tool with an explicit unanswered result and a short instruction in the turn language to continue with stated assumptions, record the skipped response in history, and SHALL NOT fabricate a choice, text answer, or a new user turn. A tool-approval prompt SHALL retain its own approval choices and SHALL NOT gain this skip action.

#### Scenario: Skip a poorly posed question

- **WHEN** the person skips a pending agent question
- **THEN** the agent receives an explicit skipped result and can continue the turn, and reloading the conversation does not restore that question as pending

#### Scenario: Close a question

- **WHEN** managed chat displays a pending agent question
- **THEN** the card shows no top-right close control, and the person closes a single question with the skip action, with the same result as before

#### Scenario: Skip every grouped question

- **GIVEN** several agent questions are grouped in one card
- **WHEN** the person chooses "Skip all"
- **THEN** every pending question is skipped in one batch, including questions with drafted answers, and the agent continues the same turn

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

Several `ask_user` calls in one turn SHALL each retain a distinct occurrence identity, and each answer SHALL return to its own call. A complete set of simultaneous agent-question answers SHALL be accepted in one resume request only when every answer matches a pending occurrence; rejection SHALL leave the checkpoint and editable answers intact. History and reload SHALL preserve each response and any remaining pending questions.

#### Scenario: Sibling questions

- **GIVEN** two agent questions from one turn share a runtime interrupt identifier
- **WHEN** the first is answered
- **THEN** its result belongs to the first call and the second remains answerable

#### Scenario: Reload during several questions

- **GIVEN** the first question in a turn was answered and a second is pending
- **WHEN** the conversation is reloaded
- **THEN** the second question is restored as the only pending question

#### Scenario: Complete batch of sibling answers

- **GIVEN** several agent questions are pending on one checkpoint
- **WHEN** the person submits one answer or skip for every pending occurrence
- **THEN** the runtime validates and claims the complete set atomically, resumes the graph once, and stores a separate answer for each occurrence
- **AND** an incomplete or invalid batch leaves every pending question answerable

### Requirement: Graph choice questions preserve their response contract

The Graph choice helper SHALL accept the enriched human response form without losing the selected option, while existing callers that expect an optional option identifier SHALL continue to behave as before.

#### Scenario: Existing Graph choice caller

- **WHEN** an existing Graph choice step receives an answer carrying an offered option identifier
- **THEN** it returns the same identifier it returned before this change

### Requirement: HITL cards follow the design system

Managed chat's human-input cards, which cover agent questions, tool approvals, Graph questions and their answer records, SHALL take their text styles, colours, spacing and corner radii from design-system tokens, with no hard-coded font size, colour mix or spacing. Layout widths, for which the design system has no token, are excepted. Inner controls SHALL use a smaller corner radius than the card that contains them. Choices SHALL use a muted outline at rest and a stronger outline on hover. Their label SHALL use the main text colour, except on a tool approval, where the accept label SHALL use the success colour and the refuse label the error colour, both in an emphasized text style, while every other approval choice keeps the main text colour. The question SHALL read as the card's header, on a contrasting full-width band; with several questions, the question tabs SHALL sit above that band.

#### Scenario: Choice styling

- **WHEN** managed chat displays the choices of an agent question, a Graph question or a tool approval
- **THEN** each choice spans the card width with left-aligned text, a muted outline at rest, a stronger outline on hover, and the same height for the same content

#### Scenario: Tool approval emphasis

- **WHEN** managed chat displays a tool execution approval
- **THEN** the accept label appears in the success colour and the refuse label in the error colour, in an emphasized text style, while the choices otherwise look like any other choice
- **AND** "Approve for this conversation" keeps the main text colour

#### Scenario: Question header

- **WHEN** managed chat displays an agent question, a Graph question or a tool approval
- **THEN** its title and question appear together in a full-width band at the top of the card, on a contrasting surface, in an emphasized text style
- **AND** with several grouped questions, the compact question tabs sit above that band, which shows the selected question

#### Scenario: Keyboard answers

- **WHEN** managed chat displays an unanswered question or tool approval with choices
- **THEN** each choice starts with a badge showing its number, and pressing that number picks it
- **AND** Enter sends grouped answers when they can be sent, and Escape skips an agent question
- **AND** these keys do nothing while the person types in a field or the card is busy or read-only, Escape does nothing while a drawer or dialog is open, and the card never takes focus by itself

#### Scenario: Both themes

- **WHEN** the person uses the light or dark theme
- **THEN** every card, choice, label and icon takes its colour from that theme's tokens, and text remains readable against its background
