## ADDED Requirements

### Requirement: The composer accepts several prompt commands in one message

In managed chat, the slash menu SHALL keep offering prompt commands, from the chat team and from the personal space, when the message already holds one or more prompt commands, at any position where a command can be typed. Each completed prompt command SHALL be its own token: one block for the caret, selection and deletion, with its own source hint and its own preview of the prompt it was picked from. Editing or removing one token SHALL leave the other prompt and skill tokens recognised. A message SHALL hold at most 16 prompt commands; a message holding more SHALL NOT be sent and the user SHALL be told the limit. This requirement supersedes any earlier statement that a message carries a single prompt command.

#### Scenario: The menu still offers prompts after a first one

- **GIVEN** the composer holds the prompt token `/summary` followed by a space
- **WHEN** the user types `/`
- **THEN** the menu lists the team's and the personal prompt commands under their sections, alongside the platform skills

#### Scenario: Two prompt tokens with their own preview

- **GIVEN** the user picked `/summary` from the team section and `/tone` from the personal section
- **WHEN** the user activates the `/tone` token
- **THEN** the side panel shows the name, the command and the current text of the personal `tone` prompt
- **AND** activating the `/summary` token then shows the team `summary` prompt instead

#### Scenario: Removing one token keeps the other

- **GIVEN** a message holding the tokens `/summary` and `/tone`
- **WHEN** the user deletes the `/summary` token with one Backspace
- **THEN** `/tone` is still a token, picked from the same library as before

#### Scenario: Too many prompt commands

- **GIVEN** a message holding 17 prompt commands
- **WHEN** the user submits it
- **THEN** nothing is sent, the draft is kept and a message says a message can hold at most 16 commands

### Requirement: Every prompt command expands in place when the message is sent

On submit, the web client SHALL read every prompt behind a prompt command of the message from its owning library and SHALL replace each command by that prompt's text at the command's position, keeping the order of the message and the user's own text on its side of each prompt. The model SHALL receive that assembled text and nothing about commands. Platform skills selected in the same message SHALL be requested together, as before. Resolution SHALL be all or nothing: when any prompt cannot be read, is empty, is no longer in its catalog or was picked for another agent, team or personal space, no turn SHALL be sent, no skills-only turn SHALL be sent, the draft SHALL be kept, and the error SHALL name the command it is about and say whether to choose it again or to retry. The message length limit SHALL apply to the assembled text.

#### Scenario: Two prompts expand in order

- **GIVEN** `/summary` whose prompt text is `Summarise the document.` and `/tone` whose prompt text is `Use a formal tone.`
- **WHEN** the user submits `First /summary then /tone please`
- **THEN** the turn's text reads, in this order: `First`, `Summarise the document.`, `then`, `Use a formal tone.`, `please`
- **AND** neither `/summary` nor `/tone` appears in the text the model receives

#### Scenario: Prompts and skills in one message

- **GIVEN** two prompt commands and the platform skill `/verify-answer` in one message
- **WHEN** the user submits it
- **THEN** both prompt texts reach the model and the skill name travels with the turn as it does today

#### Scenario: One stale prompt holds the whole message back

- **GIVEN** a message holding `/summary` and `/tone`, and the `tone` prompt was deleted since it was picked
- **WHEN** the user submits it
- **THEN** nothing is sent and the draft is unchanged
- **AND** the error says that `/tone` is no longer available and must be removed and chosen again

#### Scenario: One unreadable prompt asks to retry

- **GIVEN** a message holding `/summary` and `/tone`, and reading `tone` fails with a server error
- **WHEN** the user submits it
- **THEN** nothing is sent and the error says that `/tone` could not be read and to try again in a moment

#### Scenario: The limit counts what is sent

- **GIVEN** a short typed line whose two prompts expand to more characters than the message limit
- **WHEN** the user submits it
- **THEN** nothing is sent and the error states the limit

### Requirement: The command descriptor lists every prompt command of the turn

A turn sent with one or more prompt commands SHALL carry, in its command descriptor, an optional list named `prompts` with one entry per prompt command occurrence, in the order of the typed line. Each entry SHALL give the command, the prompt's id and name, the position of the command in the typed line, and the position and length of that prompt's text in the text that was sent. Positions SHALL be counted as the web client counts string positions (UTF-16 code units), like the existing draft offset; the runtime SHALL NOT interpret them. The descriptor's existing single fields SHALL stay and SHALL describe the first prompt command of the line, with the user's own text as its appended text. The list SHALL be additive and optional on the execution request and on the stored turn: a request without it SHALL be accepted, and a turn stored without it SHALL be served unchanged. The runtime SHALL accept at most 16 entries and SHALL reject a request whose list is longer or malformed, as it does for any invalid request field. The list SHALL be stored and served back with the turn as it was sent. It SHALL remain side data: client-supplied, used for display only, never a source of text for the model and never resolved against the prompt library at display time.

#### Scenario: Two prompts are listed with their positions

- **WHEN** the user sends `First /summary then /tone please` with both prompts resolved
- **THEN** the stored turn's descriptor lists `summary` then `tone`, each with its prompt id and name, its position in the typed line and the position and length of its text in the stored text
- **AND** the single fields name `summary`, its prompt id and its position

#### Scenario: A single prompt is listed too

- **WHEN** the user sends `/summary the report`
- **THEN** the descriptor lists one entry for `summary` and its single fields are what they are today

#### Scenario: A request without the list is accepted

- **GIVEN** a client that sends the descriptor with its single fields only
- **WHEN** the turn is executed and stored
- **THEN** the request is accepted and the stored descriptor has no list

#### Scenario: An oversized list is rejected

- **WHEN** a request carries a descriptor listing 17 prompts
- **THEN** the runtime rejects the request as invalid and runs no turn

#### Scenario: The list survives a reload

- **GIVEN** a stored turn whose descriptor lists two prompts
- **WHEN** the conversation history is read again
- **THEN** the served descriptor carries the same two entries

### Requirement: A sent message shows one badge per prompt command, each opening its own prompt text

The transcript SHALL render a sent message as the line the user typed, with one prompt badge per listed prompt command at its position and the platform skill badges at theirs. Activating a prompt badge SHALL open the side panel on that prompt alone: its name, its `/command`, then the part of the stored text that came from that prompt. The panel SHALL NOT show the user's own words or another prompt's text under that prompt's name, and SHALL NOT read the prompt library. Copying the message SHALL give the line the user typed. A stored descriptor whose list does not fit the stored turn (a position outside the text, a command not found at its position in the typed line, entries out of order or overlapping) SHALL be ignored as a whole and the message SHALL render from the single fields.

#### Scenario: Two badges at their positions

- **GIVEN** a stored turn sent as `First /summary then /tone please`
- **WHEN** the conversation is displayed, live or after a reload
- **THEN** the bubble reads `First`, a `/summary` badge, `then`, a `/tone` badge, `please`
- **AND** no prompt text is shown in the bubble

#### Scenario: A badge opens its own prompt text

- **GIVEN** that message
- **WHEN** the user activates the `/tone` badge
- **THEN** the panel shows the name of the `tone` prompt, `/tone` and `Use a formal tone.`
- **AND** it shows neither `First`, `then`, `please` nor the text of `summary`

#### Scenario: A single prompt no longer shows the user's words

- **GIVEN** a turn sent after this change as `/summary the report`
- **WHEN** the user activates its badge
- **THEN** the panel shows the prompt's text without `the report`

#### Scenario: The prompt changed after the message was sent

- **GIVEN** a sent message with two prompt badges, and one of the prompts was edited or deleted since
- **WHEN** the user activates its badge
- **THEN** the panel shows the text that was sent, with no error

#### Scenario: Copy gives the typed line

- **WHEN** the user copies that message
- **THEN** the clipboard holds `First /summary then /tone please`

#### Scenario: A list that does not fit the turn is ignored

- **GIVEN** a stored descriptor whose list points outside the stored text
- **WHEN** the conversation is displayed
- **THEN** the message renders as a single-prompt turn from the single fields, with no error

### Requirement: Recall restores every prompt command of a sent message

Recalling a sent message SHALL put the typed line back in the composer and SHALL restore each listed prompt command as a token bound to the prompt it was sent with (its id, at its position), alongside the selected skills. Submitting the recalled line unchanged SHALL resolve each prompt from the currently authorised catalogs by that id, with no fallback to a prompt of the same name; a prompt that is no longer available SHALL hold the message back as on any submit. Two sent messages with the same typed line but different prompts SHALL remain separately recallable.

#### Scenario: Recall two prompts picked from different libraries

- **GIVEN** a sent message where `/summary` came from the team and `/summary-2` from the personal space
- **WHEN** the user recalls it and submits it unchanged
- **THEN** both tokens are restored and the same two prompts are read from their own libraries

#### Scenario: A recalled prompt was deleted

- **GIVEN** a recalled message with two prompt tokens, one of whose prompts was deleted
- **WHEN** the user submits it
- **THEN** nothing is sent and the error names that command

#### Scenario: Same line, different prompts

- **GIVEN** two sent messages typed `/summary` that ran the team prompt and the personal prompt
- **WHEN** the user browses the sent messages with ArrowUp
- **THEN** both are offered, each restoring its own prompt

### Requirement: Hand-typed prompt commands resolve one by one

A prompt command typed in full without picking a row SHALL be recognised and resolved for each occurrence on its own, with the rules that hold for a single one: the chat team's command first, then the personal one; no personal fallback while the team catalog has not answered; exact, case-sensitive name. A typed name that is also a platform skill SHALL keep the existing precedence: delimited, it is a skill selection, unless the user picked the prompt row for that token. Picked and typed prompt commands SHALL mix freely in one message.

#### Scenario: Two typed names from two libraries

- **GIVEN** `/summary` exists only in the team and `/tone` only in the personal space
- **WHEN** the user types `/summary and /tone now` in full and submits
- **THEN** both prompts are read, the first from the team and the second from the personal space, and both expand in place

#### Scenario: A homonym resolves per name

- **GIVEN** `/summary` exists in the team and in the personal space
- **WHEN** the user types it twice without picking a row and submits
- **THEN** both occurrences run the team's prompt

#### Scenario: Team catalog still loading

- **GIVEN** a message with a picked team prompt and a typed `/tone` known only in the personal space, while the team catalog has not answered
- **WHEN** the user submits
- **THEN** nothing is sent and the error says that `/tone` could not be read and to try again

#### Scenario: A typed skill homonym stays a skill

- **GIVEN** a platform skill and a prompt both named `review`
- **WHEN** the user types `/summary then /review the text` without picking a row for `review`, and submits
- **THEN** `summary` expands as a prompt and `review` travels as a skill selection, not as a prompt

### Requirement: Single-prompt turns and older readers are unaffected

A turn stored before this change, whose descriptor has only the single fields, SHALL render, open its panel, copy and recall exactly as before. A reader that knows only the single fields SHALL still render a turn that lists several prompts: the first prompt as a badge at its position, the rest of the typed line as text, and the whole sent text in the panel. A turn stored by a runtime that does not know the list SHALL be stored and served with its single fields, and SHALL render that same way.

#### Scenario: An old conversation

- **GIVEN** a conversation whose command turns were stored before this change
- **WHEN** it is opened
- **THEN** each of those turns shows one badge, and its panel shows the whole text that was sent, as today

#### Scenario: A reader that ignores the list

- **GIVEN** a stored turn listing two prompts, read by a client that knows only the single fields
- **WHEN** it is displayed
- **THEN** the first prompt shows as a badge, the second as the `/name` the user typed, and nothing errors

#### Scenario: A runtime that does not know the list

- **GIVEN** a turn with two prompt commands sent to a runtime that predates the list
- **WHEN** the turn runs and the conversation is reloaded
- **THEN** the agent received the full assembled text of both prompts
- **AND** the reloaded message shows the first prompt as a badge and the second as the `/name` the user typed

### Requirement: The same prompt command may appear more than once in a message

A prompt command present several times in one message SHALL be expanded at each occurrence, each with its own token, badge and descriptor entry. A prompt used several times SHALL be read once per submit.

#### Scenario: The same command twice

- **GIVEN** `/summary` whose prompt text is `Summarise the document.`
- **WHEN** the user submits `/summary of A, /summary of B`
- **THEN** the sent text holds `Summarise the document.` twice, each followed by its own words
- **AND** the message shows two `/summary` badges and the prompt was read once

### Requirement: The first prompt command names the conversation

When the first message of a conversation holds prompt commands, the conversation's title SHALL be built from the name of the first prompt command of the line, followed by the user's own text, as it is today for a single command.

#### Scenario: A new conversation started with two prompts

- **GIVEN** `/summary` is the command of the prompt named `Weekly review`
- **WHEN** a new conversation starts with `/summary /tone the Q3 report`
- **THEN** the conversation's title starts with `Weekly review` and continues with `the Q3 report`

### Requirement: Running prompt commands leaves prompt use counters unchanged

Sending a message with one or several prompt commands SHALL NOT change a prompt's use counters, as is the case today for a single command. Copying a prompt from the library, choosing it in an agent form and attaching it to a conversation SHALL keep counting as they do.

#### Scenario: Two commands run

- **GIVEN** two prompts with known use counters
- **WHEN** the user sends a message that runs both through their commands
- **THEN** neither counter changes
