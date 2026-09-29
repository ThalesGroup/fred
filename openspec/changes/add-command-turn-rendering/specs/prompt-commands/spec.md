## ADDED Requirements

### Requirement: A turn that ran a command SHALL store the text that was sent

The stored content of a turn that ran a command SHALL be the full assembled
text: the prompt's own text followed by whatever the user appended after the
command. It SHALL NOT be the command, and it SHALL NOT be a reference to the
prompt.

History is replayed to the model on every later turn, so a turn holding only
its command would leave the model reading something it knows nothing about.

#### Scenario: The assembled text is what is stored

- **GIVEN** a prompt whose command is `summary` and whose text is
  `Résume le document et rédige une synthèse de :`
- **WHEN** the user runs `/summary 33 lignes`
- **THEN** the stored turn's content is
  `Résume le document et rédige une synthèse de : 33 lignes`
- **AND** it contains neither `/summary` alone nor a reference to the prompt

#### Scenario: The agent receives an ordinary turn

- **WHEN** a command turn is sent
- **THEN** the agent receives the assembled text
- **AND** nothing about commands reaches the agent

### Requirement: A turn that ran a command SHALL carry a command descriptor

Such a turn SHALL carry, beside its content, a descriptor naming the command
that was run, the text the user appended after it, and the id and name of the
prompt. The descriptor SHALL be side data: never rendered raw, and never the
source of the text sent to the model.

A turn that ran no command SHALL carry no descriptor and SHALL be unaffected.

#### Scenario: Descriptor recorded alongside the content

- **WHEN** the user runs `/summary 33 lignes`
- **THEN** the turn carries a descriptor whose command is `summary`
- **AND** whose appended text is `33 lignes`
- **AND** which names the prompt's id and its name

#### Scenario: A command run with nothing appended

- **WHEN** the user runs `/summary` with no trailing text
- **THEN** the descriptor's appended text is empty
- **AND** the stored content is the prompt's text alone

#### Scenario: An ordinary turn carries nothing extra

- **WHEN** the user sends text they typed themselves
- **THEN** the turn carries no command descriptor

### Requirement: The transcript SHALL render a command turn as its command

Where a turn carries a command descriptor, the transcript SHALL render a
command component in place of the turn's text, showing the command and any
appended text. The prompt's text SHALL NOT appear in the chat body.

#### Scenario: The chat body shows the command, not the prompt

- **GIVEN** a stored turn whose content is a long prompt text and whose
  descriptor names the command `summary`
- **WHEN** the conversation is displayed
- **THEN** the turn shows `summary` and the appended text
- **AND** the prompt's text is not shown in the chat body

#### Scenario: A reloaded conversation renders the same way

- **WHEN** a conversation containing a command turn is reopened
- **THEN** that turn renders as the command component again, not as text

### Requirement: Opening a command turn SHALL show the text that was sent

Activating the command component SHALL show, in the side panel, the turn's own
stored content. It SHALL NOT resolve the prompt by id at display time.

A prompt's text is overwritten on edit and the repository keeps no version
history, so resolving the id would show a conversation asking something it
never asked — and nothing at all once the prompt is deleted.

#### Scenario: The panel shows what was actually sent

- **GIVEN** a command turn whose stored content is the prompt text as it was
  at the time
- **WHEN** the user activates the command component
- **THEN** the panel shows that stored content

#### Scenario: The prompt has since been edited

- **GIVEN** a command turn, and the prompt behind it has since been rewritten
- **WHEN** the user activates the command component
- **THEN** the panel shows the text the turn actually sent, not the new text

#### Scenario: The prompt has since been deleted

- **GIVEN** a command turn whose prompt no longer exists
- **WHEN** the user activates the command component
- **THEN** the panel still shows the text the turn sent
- **AND** nothing reports an error

### Requirement: A reader that does not know the descriptor SHALL still render the turn

A client unaware of the command descriptor SHALL render the turn as an
ordinary text turn. The descriptor SHALL be additive: its absence, or its
presence to an unaware reader, SHALL NOT break the conversation.

#### Scenario: An unaware reader degrades to text

- **GIVEN** a stored turn carrying a command descriptor
- **WHEN** it is read by a client that does not know the descriptor
- **THEN** the turn renders as its plain assembled text
- **AND** nothing errors
