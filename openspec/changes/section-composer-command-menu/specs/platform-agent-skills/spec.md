## REMOVED Requirements

### Requirement: ReAct slash commands combine platform skills and two prompt libraries

**Reason**: Personal prompt commands are no longer limited to ReAct agents, and sources are shown by section instead of per-row labels. Replaced by "Slash commands combine platform skills and two prompt libraries" below.
**Migration**: None. Every scenario is carried over to the replacing requirement, with the ReAct condition lifted.

## ADDED Requirements

### Requirement: Slash commands combine platform skills and two prompt libraries

For managed chat, whatever the agent's execution family, the slash menu SHALL offer prompts carrying commands from the current chat team and from the caller's personal library, alongside the platform skills the selected runtime provides. The menu SHALL identify each entry's source by the section it is listed under and preserve independently selectable homonyms. A personal chat SHALL offer its personal prompt library once. Prompts without commands SHALL remain available through the existing library panel. This requirement SHALL NOT change which agents are offered platform skills. Available prompt commands SHALL complete, render and resolve inline before or after selected skills in all managed chats, with the same prompt container treatment in the draft and sent history.

#### Scenario: Team chat offers three sources

- **GIVEN** a team agent of any execution family, a personal prompt command and a team prompt command
- **WHEN** the authorized user types `/`
- **THEN** the menu offers both prompt commands alongside the runtime's platform skills, each under the section of its source
- **AND** personal data is queried under the caller's own personal scope and team prompts under the chat team

#### Scenario: Duplicate prompt commands retain their source

- **GIVEN** personal and team libraries both contain `/summary`
- **WHEN** the user selects either prompt row and submits after completion
- **THEN** the exact selected prompt is fetched from its owning library and its text reaches the agent with the existing command attribution
- **AND** a typed prompt command without an explicit selection resolves the chat team's match first, then the personal match

#### Scenario: Skills and prompt commands remain separate

- **GIVEN** a platform skill and a prompt share a name
- **WHEN** the user explicitly selects the prompt row
- **THEN** prompt text is submitted through the existing prompt-command path without a typed skill selection
- **AND** selecting the skill row completes its canonical invocation without sending and subsequent submission uses the unchanged ReAct skill-loading path
- **AND** typing/paste retains existing delimited-skill precedence

#### Scenario: Personal scope is not duplicated or carried between chats

- **WHEN** a personal chat opens or the active team or agent changes
- **THEN** each eligible prompt source appears once and prior selections and cached responses do not dispatch another scope's prompt
- **AND** failed reads or unavailable personal identity do not fall back to a different selected prompt; an invalidated completed choice requires command editing or reselection

#### Scenario: Pending team discovery cannot change typed precedence

- **GIVEN** the personal command catalog is available while the chat team's catalog is unresolved
- **WHEN** the user submits a typed prompt command without explicitly selecting a row
- **THEN** personal fallback is refused until the team's absence of that command is established
- **AND** an explicit personal row selection remains independently usable while team discovery is pending

#### Scenario: Personal commands do not depend on the agent kind

- **WHEN** the selected template is ReAct, Deep, Graph, Proxy or not yet resolved
- **THEN** the caller's personal prompt commands are offered in a team chat
- **AND** the existing skill availability and skill dispatch behavior are preserved

### Requirement: The slash menu lists its entries in titled sections by source

The slash menu SHALL group its entries in up to three sections, always in this order: the chat team's prompt commands, the caller's personal prompt commands, then platform skills. Each section SHALL have a visible heading that names it for assistive technology: the team section's heading SHALL include the team's name, shown on one line and truncated with an ellipsis when too long; the personal section's heading SHALL name the personal space; the skills section's heading SHALL name platform skills. Headings SHALL NOT be uppercased. A section with no entry to show, including after filtering on the typed text, SHALL be hidden together with its heading. Rows SHALL NOT carry a source label of their own. Keyboard navigation SHALL treat all displayed entries as one continuous list in display order and SHALL stop at the first and at the last entry without wrapping.

#### Scenario: Three sections in a team chat

- **GIVEN** a team chat whose team is named "Finance", with a team prompt command, a personal prompt command and a platform skill
- **WHEN** the user types `/`
- **THEN** the menu shows a section titled with the team name "Finance", then a personal-space section, then a platform-skills section, each holding its own entries
- **AND** no row shows a source label

#### Scenario: Empty and unmatched sections are hidden

- **GIVEN** a team chat where only the personal library holds a command starting with `re`
- **WHEN** the user types `/re`
- **THEN** only the personal-space section and its heading are shown

#### Scenario: Personal chat shows one commands section

- **WHEN** the user types `/` in a personal-space chat
- **THEN** the prompt commands appear once, under the personal-space section, with no team section

#### Scenario: A shared command name appears in both sections

- **GIVEN** the team and the personal library both contain `/summary`
- **WHEN** the user types `/sum`
- **THEN** `/summary` is listed once in the team section and once in the personal-space section, and each row selects its own prompt

#### Scenario: Arrow keys cross section boundaries

- **GIVEN** the menu shows a team section followed by a personal-space section
- **WHEN** the focus is on the last team entry and the user presses ArrowDown
- **THEN** the focus moves to the first personal-space entry
- **AND** ArrowUp from the first displayed entry and ArrowDown from the last one leave the focus where it is

#### Scenario: Long team name

- **GIVEN** a team whose name is wider than the menu
- **WHEN** the menu opens
- **THEN** the team heading stays on one line and ends with an ellipsis

#### Scenario: Rows stay compact

- **GIVEN** the menu lists a prompt command and a platform skill that has an argument hint and a long description
- **WHEN** the menu is shown
- **THEN** each row shows its name above its description, the description on one line and cut with an ellipsis when too long
- **AND** hovering a row gives its full description
- **AND** the skill's argument hint is not shown in the menu

### Requirement: Invoked prompts and skills are shown as small containers

A completed prompt command or platform skill SHALL be shown as a small filled container holding its icon and name, in the composer and in sent or reopened user messages. A prompt container SHALL use the primary container colour pair whether the prompt comes from the team or from the personal space; a platform skill container SHALL use the secondary container colour pair; icon and name SHALL take the container's content colour. The container SHALL have a small corner radius and light horizontal padding and SHALL NOT change the height of the line it sits on. Where the surrounding surface has the same colour as the container, as in the user's sent message, the container SHALL remain distinguishable from that surface. Clickable containers SHALL keep their hover and keyboard-focus indication.

#### Scenario: Tokens in the composer

- **GIVEN** a draft holding a completed prompt command and a completed platform skill among ordinary text
- **WHEN** the composer shows the draft
- **THEN** the prompt appears in a primary container and the skill in a secondary container, each with its icon and name
- **AND** the line is exactly as tall as a line of plain text

#### Scenario: Badges in a sent message

- **GIVEN** a sent message that invoked a prompt command and a platform skill
- **WHEN** the conversation shows the message
- **THEN** both appear as containers with the same colours as in the composer
- **AND** each container is visibly outlined against the message bubble, whose height per line is unchanged

#### Scenario: Team and personal prompts look the same

- **WHEN** a team prompt and a personal prompt are each completed in the composer
- **THEN** both use the same prompt container

### Requirement: The composer caret stays visible in the empty field

When the chat composer is empty and focused, the text caret SHALL be fully visible, at its usual height, in front of the placeholder. The placeholder SHALL NOT be part of the editable text, SHALL remain announced to assistive technology as the field's placeholder, SHALL NOT move and SHALL leave the field at the height of one line.

#### Scenario: Caret over the placeholder

- **GIVEN** an empty composer showing its placeholder
- **WHEN** the user focuses the field
- **THEN** the whole caret is visible at the start of the line, drawn over the placeholder
- **AND** the placeholder text and the field height are the same as before focusing

### Requirement: Composer tokens behave as one block

In the chat composer, a completed prompt command or platform skill token SHALL behave as a single unit of text. The Left and Right arrow keys SHALL move the caret across a token in one press, and extending a selection SHALL take a token as a whole. Backspace with the caret right after a token, and Delete with the caret right before it, SHALL remove the whole invocation, leaving no stray slash and no doubled or leading space, and SHALL NOT reopen the command menu. Undo SHALL restore the removed token with its selection identity. Tokens next to each other SHALL each behave independently. The command menu SHALL stay closed while the caret sits right after a rendered token, prompt or skill alike, picked or typed by hand, including a token at the very end of the draft; it SHALL open as usual for a new `/` typed elsewhere or for a name still being typed with no token yet. Away from a token, the same keys SHALL keep their ordinary one-character behaviour.

#### Scenario: Arrow keys jump over a token

- **GIVEN** a draft `Before /meeting-minutes after` whose skill is shown as a token
- **WHEN** the caret is right after the token and the user presses the Left arrow once
- **THEN** the caret is right before the token
- **AND** pressing the Right arrow once puts it back right after the token

#### Scenario: Backspace removes the whole token

- **GIVEN** a draft `Before /meeting-minutes after` with the caret right after the token
- **WHEN** the user presses Backspace
- **THEN** the draft reads `Before after`, the skill is no longer selected and the command menu stays closed
- **AND** undo restores `Before /meeting-minutes after` with its token

#### Scenario: Delete removes the whole token

- **GIVEN** a draft `Before /meeting-minutes after` with the caret right before the token
- **WHEN** the user presses Delete
- **THEN** the draft reads `Before after`

#### Scenario: A token typed by hand behaves like a picked one

- **GIVEN** the user typed `/summary` and a space by hand, without picking a row, and the prompt is shown as a token
- **WHEN** the user presses Backspace once
- **THEN** only the space is removed and the token is still shown
- **AND** a second Backspace removes the whole token

#### Scenario: The menu stays closed on a token at the end of the draft

- **GIVEN** a prompt token, picked in the menu or typed by hand, followed by a single space
- **WHEN** the user removes that space with Backspace
- **THEN** the token is still shown and the command menu is closed
- **AND** typing a space or text after it keeps the menu closed
- **AND** typing a new `/re` further on opens the menu for that new command only

#### Scenario: Two tokens side by side

- **GIVEN** a draft `/review /meeting-minutes notes` showing two tokens
- **WHEN** the user removes the second token with Delete
- **THEN** the draft reads `/review notes` and the first token is still selected

## MODIFIED Requirements

### Requirement: Web users can require a skill for their request

Managed web chat SHALL accept `/<name> [request]` at the invocation position and retain `/skill <name> [request]` compatibility and offer skill-name autocompletion from the selected agent's actual runtime catalog. Submission SHALL transmit typed name-only skill selections and the complete canonical user text including every invocation at its original position; for ReAct, the server SHALL validate and load the selected skill before the first model call from its snapshot rather than client instructions. Deep SHALL use the canonical request as ordinary user text, without Fred preload or snapshot body validation; native model choice SHALL determine instruction/reference reads. A named invocation SHALL remain valid without arguments, even if the skill requires information to finish. Argument hints SHALL be optional descriptive text, never submission requirements. A bare `/skill` SHALL offer selection guidance without launching an empty agent turn. An unknown, invalid or unavailable explicit ReAct selection SHALL fail clearly before any model call, with no fallback to another skill or a prompt command.

#### Scenario: Explicit load precedes inference

- **WHEN** an authorized user submits `/meeting-minutes prepare the minutes from these notes` to ReAct
- **THEN** the runtime loads `meeting-minutes` before its first model call
- **AND** the model receives those instructions and the complete request

#### Scenario: Explicit Deep selection follows native loading

- **WHEN** an authorized user submits `/meeting-minutes prepare the minutes from these notes` to Deep
- **THEN** the first inference receives the canonical user message and upstream skill metadata, without a Fred-loaded instruction message or user-origin load event
- **AND** the model can read `/skills/meeting-minutes/SKILL.md` and its references with native `read_file`, with actual reads retaining user-origin events/KPI for the selected name and agent origin otherwise
- **AND** invoke, streaming, checkpoint follow-up and HITL resume use the same native behavior
- **AND** platform guidance identifies a matching slash command as the user's request to apply the procedure and directs instruction and required reference reads before drafting or using task tools, without adding a preload or forced tool call
- **AND** the current name-only selections appear as a user-request reminder in the existing per-turn system context, without paths, skill bodies or another catalog; fresh turns without selections remove it and same-exchange resumes retain it

#### Scenario: Discover skills directly from the slash menu

- **WHEN** an authorized web user types `/` in the composer
- **THEN** every skill from the selected runtime catalog is offered directly, alongside prompt commands
- **AND** a prefix such as `/comp` filters those skill names without requiring `/skill` first
- **AND** selecting a skill completes the canonical invocation without sending a turn or losing existing request text
- **AND** prompt and skill entries sharing a name remain independently selectable
- **AND** no standalone `/skill` dispatcher row is shown; named skills use a distinct platform pictogram and localized origin hint
- **AND** hovering the selected or sent skill name shows its description from the current runtime catalog when available, with its platform origin

#### Scenario: Named invocation without arguments

- **WHEN** a user submits `/meeting-minutes` without meeting notes in context
- **THEN** the turn starts; ReAct preloads instructions before inference, while Deep uses native metadata and model-driven instruction reads
- **AND** the agent is guided to ask for notes rather than invent meeting content
- **AND** a supplied `argument-hint` does not prevent submission

#### Scenario: Attach a skill to existing draft text

- **GIVEN** a request already contains text, including multiple lines
- **WHEN** the user types a skill command at the caret before, after or within that text and selects a skill
- **THEN** only the active command range is replaced and the existing request text is preserved
- **AND** the selected name stays at the invocation position using canonical `/<name>` text, with no turn dispatched by completion

#### Scenario: Direct typing and manual copy

- **WHEN** a current catalog name is typed or pasted as `/<name>` at a whitespace boundary and followed by whitespace
- **THEN** it becomes a selected skill at that position without dispatching a turn
- **AND** copying the displayed skill alone or the entire message preserves the canonical slash invocation
- **AND** complete delimited skill names take precedence for typing/paste; explicitly choosing a prompt homonym retains prompt behavior

#### Scenario: Inline wrapping and scrolling

- **GIVEN** a skill is selected in a multiline or overflowing request
- **WHEN** the text wraps, contains a newline or is scrolled
- **THEN** subsequent lines start at the normal left text inset and the inline skill scrolls with the line where it was inserted
- **AND** a sent skill label and request share the same text baseline

#### Scenario: Selected skill argument placeholder

- **GIVEN** the composer contains a selected skill with an empty request
- **WHEN** the request field is displayed
- **THEN** its placeholder shows the skill's argument hint when supplied, otherwise the generic optional-request prompt
- **AND** the hint is not inserted into the request and does not prevent empty submission

#### Scenario: Optional argument hints

- **GIVEN** one valid skill supplies `argument-hint` and another omits it
- **WHEN** either skill is selected in the composer
- **THEN** the supplied hint is shown as advisory text after the selected skill, not in the suggestion list, and both skills are usable
- **AND** non-string, blank or over-256-character hints are omitted with bounded diagnostics while retaining the valid skill

#### Scenario: Skill badge in the composer and user message

- **WHEN** a user completes a known `/<name>` selection or types a whitespace-delimited known name
- **THEN** the composer shows an icon/name token inline with the editable request, as a small filled container with the complete name visible and no separate row or removal button, allowing submission without extra text
- **AND** the token is edited as one block: it cannot be entered with the keyboard, and removing it removes the whole invocation while preserving surrounding text; deleting surrounding request text does not remove the skill
- **AND** persisted name-only selection metadata lets the sent user bubble display the same skill badge alongside its request, including after reopening history without the current catalog
- **AND** Deep selection metadata preserves the badge/preview without a preload event, instruction injection or load count; native agent-origin reads do not select ordinary user mentions
- **AND** automatic agent/child loads and ordinary messages merely mentioning `/skill` do not label the user turn as explicitly selected
- **AND** copying a selected user turn includes the skill invocation and request

#### Scenario: Existing empty-request representation

- **GIVEN** a selected skill's stored question is exactly `/skill <name>`
- **WHEN** the user message is rendered or copied
- **THEN** the UI interprets the stored question as the existing no-request sentinel, shows the skill label alone, and copies canonical `/<name>` text
- **AND** a literal request identical to that sentinel remains indistinguishable under the existing name-only wire representation; all other request text is retained

#### Scenario: Stale menu or forged selection

- **WHEN** a submitted ReAct name is unavailable in the serving pod's validated snapshot
- **THEN** the runtime reports an explicit selection error and does not call the model

#### Scenario: Keyboard and agent switching

- **WHEN** the user types the skill prefix and navigates the suggestions
- **THEN** arrow keys, completion, submission and dismissal work through the existing composer interaction
- **AND** switching the selected agent invalidates suggestions from the previous runtime
