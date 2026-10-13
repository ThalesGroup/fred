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

- **GIVEN** a team chat where only the personal library holds a command whose name contains `re`
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

### Requirement: Picking a menu row inserts the command and never sends

In the slash menu, Enter, Tab and a pointer activation on a row SHALL all do the same thing, for a prompt command and for a platform skill alike: insert the row's command in the composer at the command being typed, keep the surrounding text, close the menu and send nothing. A turn SHALL only be sent by the ordinary submit, with the menu closed: Enter again, or the send button. That submit SHALL resolve a picked prompt command to the exact prompt of the picked row (its id and its owning library) and send the same expanded text and the same command attribution whichever way the row was picked. Shift+Enter SHALL keep its ordinary composer behaviour while the menu is open. Because Enter on a row sends nothing, the menu SHALL receive it whether or not sending is possible at that moment (an attachment still uploading, a draft over the length limit): the row is inserted and no line break is added. Picking a row SHALL replace the whole name under the caret, whatever its case, including the part of the name that follows the caret.

#### Scenario: Enter inserts while sending is blocked

- **GIVEN** an attachment is still uploading, or the draft is over the length limit, and the menu is open on `/su` with `/summary` focused
- **WHEN** the user presses Enter
- **THEN** the composer reads `/summary ` with the command shown as a token, no line break is added and no turn is sent

#### Scenario: The whole name under the caret is replaced

- **GIVEN** the draft `hello /MAR` with the caret between `A` and `R`, and the menu listing `/summary`
- **WHEN** the user picks `/summary`
- **THEN** the draft reads `hello /summary ` with nothing left of the typed name

#### Scenario: Enter on a prompt row inserts it

- **GIVEN** the menu is open on `/su` with the prompt command `/summary` focused
- **WHEN** the user presses Enter
- **THEN** the composer reads `/summary ` with the command shown as a token, the menu is closed and no turn is sent

#### Scenario: A second Enter sends

- **GIVEN** a prompt command was inserted from the menu with Enter
- **WHEN** the user presses Enter again
- **THEN** the turn is sent with the prompt's text in place of the command and the command attribution of the picked prompt

#### Scenario: Enter and Tab reach the same send

- **GIVEN** the same draft and the same focused prompt row
- **WHEN** the row is picked once with Enter and once with Tab, each followed by Enter
- **THEN** both turns carry the same text and the same command attribution

### Requirement: The slash menu searches inside command names

The slash menu SHALL match the typed text against the command name only, never against a prompt's name or description. The match SHALL ignore case and SHALL accept the typed text anywhere inside the name. Inside each section, entries whose name starts with the typed text SHALL be listed before the others, and each of the two groups SHALL keep the order the catalog returned. Sections SHALL keep their order and their entries SHALL stay grouped, so keyboard navigation follows the displayed order. When the menu opens or the typed text changes, the focus SHALL be on the first row displayed, whichever section holds an entry starting with the typed text. A command typed in full by hand SHALL still be recognised only in its exact, lowercase spelling.

#### Scenario: Match inside a name, whatever the case

- **GIVEN** the commands `/search` and `/summary`
- **WHEN** the user types `/MAR`
- **THEN** the menu lists `/summary` only

#### Scenario: The description is not searched

- **GIVEN** a command `/search` whose description is "Chercher"
- **WHEN** the user types `/cher`
- **THEN** the menu says that no command matches

#### Scenario: Names starting with the text come first in each section

- **GIVEN** the team commands `/pre-sum` and `/big-sum`, and the personal commands `/my-sum`, `/sum-up` and `/sum`, in that catalog order
- **WHEN** the user types `/sum`
- **THEN** the team section lists `/pre-sum` then `/big-sum`, and the personal section lists `/sum-up`, `/sum`, then `/my-sum`
- **AND** the focus is on `/pre-sum`, the first row displayed

### Requirement: The empty slash menu says why it is empty

When the slash menu has no row to show, it SHALL stay visible and show one status line. While a command catalog it reads has not answered yet, the line SHALL say that the commands are loading and SHALL NOT say that there is no command or no match. When every catalog has answered and none holds a command or a skill, the line SHALL say that there is no command yet and what the user can do, in words that hold in a team chat and in the personal space: add a command to one of their personal prompts, and, in a team, an editor can add one to a team prompt. When commands exist but none matches the typed text, the line SHALL say that no command matches. Rows from a catalog that has already answered SHALL be shown while another one is loading. When a catalog could not be read and has never answered, and no catalog is loading, the line SHALL say that the commands could not be loaded and how to retry, and SHALL NOT say that there is no command or no match; the failed catalog SHALL be asked again each time the user starts a new command, not on each character of its name.

#### Scenario: Catalogs still loading

- **GIVEN** the team's command catalog has not answered yet and nothing else is available
- **WHEN** the user types `/`
- **THEN** the menu shows a loading line and does not claim that there is no command

#### Scenario: Nothing exists

- **GIVEN** every catalog has answered and there is no team command, no personal command and no skill
- **WHEN** the user types `/`
- **THEN** the menu says there is no command yet and how to add one, with the same text in a team chat and in the personal space

#### Scenario: Nothing matches

- **GIVEN** commands exist
- **WHEN** the user types `/zzz`
- **THEN** the menu says that no command matches

#### Scenario: A catalog could not be read

- **GIVEN** reading the team's command catalog failed and nothing else is available
- **WHEN** the user types `/`
- **THEN** the menu says that the commands could not be loaded and to type `/` again to retry, and the catalog is asked again once
- **AND** typing further characters of the name does not ask it again

### Requirement: Sending waits for the command catalogs

Submitting a message SHALL never race the command catalogs (the team's prompt commands, the personal prompt commands and the agent's platform skills). A `/name`-shaped word is a slash followed by a name, delimited on both sides by whitespace or a text boundary. When the draft holds at least one such word that the user did not pick from the menu, and a catalog has not answered yet, the submit SHALL wait for every such catalog before resolving the message, then resolve it as usual; it SHALL NOT send the draft as typed in the meantime and SHALL NOT show an error for the wait. A catalog whose read had failed SHALL be asked once more at that moment. Only when a catalog still has no answer after that SHALL the message be held back, with the "try again in a moment" message naming the first typed command. A word that matches no command once the catalogs have answered SHALL be sent as plain text, with no message to the user. A draft with no such word, or whose commands were all picked from the menu, SHALL NOT wait. A second submit while one is waiting SHALL send nothing more, and a wait that ends after the chat's team, agent or personal space changed SHALL send nothing.

#### Scenario: A typed personal command while the personal catalog loads

- **GIVEN** a team chat where `/summary` is a team command and `/tone` a personal one, and the personal catalog has not answered yet
- **WHEN** the user submits `/summary and /tone now`
- **THEN** nothing is sent until the personal catalog answers
- **AND** the turn then expands both prompts, and the model never receives the literal `/tone`

#### Scenario: Right after the page loads

- **GIVEN** neither prompt catalog has answered yet
- **WHEN** the user submits `/summary report`
- **THEN** nothing is sent until both have answered, and the turn then carries the `summary` prompt
- **AND** pressing Enter a second time while waiting does not send a second turn

#### Scenario: A typed skill while the skill catalog loads

- **GIVEN** the agent's skill catalog has not answered yet
- **WHEN** the user submits `/review notes`
- **THEN** nothing is sent until it answers, and the turn then requires the `review` skill

#### Scenario: Ordinary text that starts with a slash

- **GIVEN** a catalog that has not answered yet, and no command named `nosuch`
- **WHEN** the user submits `see /etc and /nosuch please`
- **THEN** once the catalog has answered the message is sent as typed, and no error is shown

#### Scenario: No command-shaped word

- **GIVEN** catalogs that have not answered yet
- **WHEN** the user submits `see /etc/hosts and a/b`
- **THEN** the message is sent at once

#### Scenario: A failed catalog answers when asked again

- **GIVEN** reading the team's command catalog failed
- **WHEN** the user submits `/summary report`
- **THEN** the catalog is asked once more, it answers, and the turn carries the `summary` prompt

#### Scenario: A failed catalog fails again

- **GIVEN** reading the team's command catalog failed and fails again when asked
- **WHEN** the user submits `hello /summary report`
- **THEN** nothing is sent, the draft is kept and the message says that `/summary` could not be read and to try again in a moment

### Requirement: A command that cannot run says why

When a prompt command cannot be run on submit, the user SHALL be told which of two cases applies, and nothing SHALL be sent. When the picked prompt is no longer in its catalog (deleted, or its command renamed), when reading it is refused or it is not found, or when the token was picked for another agent, team or personal space, the message SHALL say that the command is no longer available and tell the user to remove it from the message and choose it again. When the read fails for another reason, or a catalog needed to resolve a typed command still has no answer after the submit waited for it and asked it again, the message SHALL tell the user to try again in a moment.

#### Scenario: The prompt was deleted or renamed

- **GIVEN** a prompt command picked from the menu whose prompt has since left its catalog
- **WHEN** the user submits
- **THEN** nothing is sent and the message asks to remove the command and choose it again

#### Scenario: The token belongs to another agent or team

- **GIVEN** a prompt command picked before the chat's team, agent or personal space changed
- **WHEN** the user submits
- **THEN** nothing is sent and the message asks to remove the command and choose it again

#### Scenario: A read that failed

- **GIVEN** a prompt command whose prompt exists but whose read fails with a network or server error
- **WHEN** the user submits
- **THEN** nothing is sent and the message asks to try again in a moment

### Requirement: A prompt token in the composer opens a preview of its prompt

A completed prompt command token in the composer SHALL be a control that opens a preview in the chat side panel, like a platform skill token: reachable and activated in the same way, with the same hover, press and keyboard-focus indication, and still behaving as one block of text. The panel SHALL show, from top to bottom, the prompt's name, its `/command`, then the prompt's current text, read when the panel opens from the library that owns the picked prompt; it SHALL NOT show a description. While the text is being read the panel SHALL say so, and when it cannot be read (not found, or access refused) it SHALL say so in a short message instead of showing another prompt's text. Activating the same token again SHALL close the panel. Opening or closing the preview SHALL NOT change the draft and SHALL NOT send anything. The token's hover hint SHALL name its source with the wording of the menu's section headings: the personal space, or the team with its name.

#### Scenario: Preview before sending

- **GIVEN** a draft holding the token of the team prompt "Résumé" with the command `/summary`
- **WHEN** the user activates the token
- **THEN** the side panel shows "Résumé", then `/summary`, then the prompt's current text
- **AND** the draft is unchanged and nothing is sent

#### Scenario: The prompt cannot be read

- **GIVEN** a token whose prompt was deleted, or that the user may no longer read
- **WHEN** the user activates the token
- **THEN** the panel shows the name and the command with a short message saying the prompt cannot be shown

#### Scenario: Hover hint uses the section wording

- **WHEN** the user hovers a personal prompt token and a team prompt token in a team named "Finance"
- **THEN** the hints read the personal-space heading and the "Finance" team heading, as in the menu

### Requirement: Invoked prompts and skills are shown as small containers

A completed prompt command or platform skill SHALL be shown as a small filled container holding its icon and its name, in the composer and in sent or reopened user messages. A command name SHALL always be displayed with its leading `/`, for prompts and platform skills alike, in the command menu rows, in composer tokens and in sent-message badges; the slash SHALL NOT be doubled, and the legacy `/skill <name>` form SHALL be displayed as `/<name>`. Displaying the slash SHALL NOT change the stored text, what is copied, or how a command is recognised. Every container SHALL use the same colour pair, the secondary container one, for a platform skill and for a prompt whether it comes from the team or from the personal space, so that a prompt and a skill differ by their icon only; icon and name SHALL take the container's content colour. The container SHALL have a small corner radius and light horizontal padding and SHALL NOT change the height of the line it sits on. In the user's sent message, whose bubble has the same colour as the container, the container SHALL carry a thin outline that keeps it distinguishable without changing its size. Clickable containers SHALL keep their hover and keyboard-focus indication.

#### Scenario: Tokens in the composer

- **GIVEN** a draft holding a completed prompt command and a completed platform skill among ordinary text
- **WHEN** the composer shows the draft
- **THEN** the prompt and the skill each appear in a container of the same colour, with their own icon and their name preceded by `/`
- **AND** the line is exactly as tall as a line of plain text

#### Scenario: Badges in a sent message

- **GIVEN** a sent message that invoked a prompt command and a platform skill
- **WHEN** the conversation shows the message
- **THEN** both appear as containers with the same colours as in the composer
- **AND** each container is visibly outlined against the message bubble, whose height per line is unchanged

#### Scenario: Every command name shows its slash

- **GIVEN** a prompt command `summary` and a platform skill `review`
- **WHEN** they are listed in the command menu, completed in the composer and shown in a sent message
- **THEN** they read `/summary` and `/review` in all three places
- **AND** copying a sent message that invoked the skill gives `/review` once, not `//review`

#### Scenario: Team and personal prompts look the same

- **WHEN** a team prompt and a personal prompt are each completed in the composer
- **THEN** both use the same container, with the prompt icon

### Requirement: The composer caret stays visible in the empty field

When the chat composer is empty and focused, the text caret SHALL be fully visible, at its usual height, in front of the placeholder. The placeholder SHALL NOT be part of the editable text, SHALL remain announced to assistive technology as the field's placeholder, SHALL NOT move and SHALL leave the field at the height of one line.

#### Scenario: Caret over the placeholder

- **GIVEN** an empty composer showing its placeholder
- **WHEN** the user focuses the field
- **THEN** the whole caret is visible at the start of the line, drawn over the placeholder
- **AND** the placeholder text and the field height are the same as before focusing

### Requirement: Composer tokens behave as one block

In the chat composer, a completed prompt command or platform skill token SHALL behave as a single unit of text. The Left and Right arrow keys SHALL move the caret across a token in one press, and extending a selection SHALL take a token as a whole. Backspace with the caret right after a token, and Delete with the caret right before it, SHALL remove the whole invocation, leaving no stray slash and no doubled or leading space, and SHALL NOT reopen the command menu. Undo SHALL restore the removed token with its selection identity. Tokens next to each other SHALL each behave independently. The command menu SHALL stay closed while the caret sits right after a rendered token, prompt or skill alike, picked or typed by hand, including a token at the very end of the draft; it SHALL open as usual for a new `/` typed elsewhere or for a name still being typed with no token yet. Away from a token, the same keys SHALL keep their ordinary one-character behaviour.

One rule SHALL decide what a token is, in the composer, on submit, when a stored message is rendered and on recall: a `/name` is a token only while whitespace or a text boundary delimits it on both sides. A character typed right before or right after a token SHALL dissolve it into plain text, which then follows the rules of a name typed by hand; removing that character SHALL NOT bring back the prompt or skill the token had been picked as. When an edit removes one token, every other token SHALL keep the prompt or skill it was picked as, including when the removed token and the one next to it read the same: the composer SHALL move tokens by the edit the editor made, not by comparing the text before and after.

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

#### Scenario: Removing the first of two tokens with the same name

- **GIVEN** a draft `/summary /summary x` whose first token was picked from the team and the second from the personal space
- **WHEN** the user removes the first token with Backspace
- **THEN** the draft reads `/summary x` and its token is the personal prompt, for the hint, the preview and the submit
- **AND** the same holds for `a /summary /summary x`, and undo restores both tokens with their own prompt

#### Scenario: A picked prompt before a skill of the same name

- **GIVEN** a draft `/review /review x` whose first token was picked as a prompt and the second as a platform skill
- **WHEN** the user removes the first token with Backspace
- **THEN** the draft reads `/review x` and its token is the skill

#### Scenario: Letters typed right after a token

- **GIVEN** the prompt token `/sum` at the end of the draft, picked from the menu, and another command `/summary`
- **WHEN** the user types `mary x` right after it
- **THEN** the draft reads `/summary x`, the `sum` prompt is no longer selected and the line is read as the `summary` command typed by hand
- **AND** submitting it sends the `summary` prompt, and the sent message shows its badge and is recalled as `/summary`

#### Scenario: A character typed right before a token

- **GIVEN** a prompt or skill token at the start of the draft
- **WHEN** the user types `x` right before it
- **THEN** the token is plain text again and submitting sends the draft as typed

#### Scenario: Removing the glued character

- **GIVEN** a picked token that a glued character turned back into text
- **WHEN** the user removes that character
- **THEN** the name is a name being typed like any other, with no token until it is delimited, and it is not bound to the prompt or skill picked earlier

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
- **THEN** the composer shows an icon/name token inline with the editable request, as a small filled container with the complete name visible after its leading slash and no separate row or removal button, allowing submission without extra text
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
