## RENAMED Requirements

- FROM: `### Requirement: ReAct slash commands combine platform skills and two prompt libraries`
- TO: `### Requirement: Slash commands combine platform skills and two prompt libraries`

## MODIFIED Requirements

### Requirement: Slash commands combine platform skills and two prompt libraries

For managed chat, whatever the agent's execution family, the slash menu SHALL offer prompts carrying commands from the current chat team and from the caller's personal library, alongside the platform skills the selected runtime provides. The menu SHALL identify each entry's source by the section it is listed under and preserve independently selectable homonyms. A personal chat SHALL offer its personal prompt library once. Prompts without commands SHALL remain available through the existing library panel. This requirement SHALL NOT change which agents are offered platform skills. Available prompt commands SHALL complete, render and resolve inline before or after selected skills in all managed chats, with the same blue prompt icon/name treatment in the draft and sent history.

#### Scenario: ReAct team chat offers three sources

- **GIVEN** a ReAct team agent, a personal prompt command and a team prompt command
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

#### Scenario: Other execution families retain current behavior

- **WHEN** the selected template is Deep, Graph, Proxy or not yet resolved as ReAct
- **THEN** the personal-plus-team command addition is enabled exactly as for a ReAct template
- **AND** the existing skill availability and skill dispatch behavior are preserved

## ADDED Requirements

### Requirement: The slash menu lists its entries in titled sections by source

The slash menu SHALL group its entries in up to three sections, always in this order: the chat team's prompt commands, the caller's personal prompt commands, then platform skills. Each section SHALL have a visible heading that names it for assistive technology: the team section's heading SHALL include the team's name, shown on one line and truncated with an ellipsis when too long; the personal section's heading SHALL name the personal space; the skills section's heading SHALL name platform skills. Headings SHALL NOT be uppercased. A section with no entry to show, including after filtering on the typed text, SHALL be hidden together with its heading. Rows SHALL NOT carry a source label of their own. Keyboard navigation SHALL treat all displayed entries as one continuous list in display order, wrapping from the last entry to the first.

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
- **AND** ArrowUp from the first displayed entry moves to the last displayed entry

#### Scenario: Long team name

- **GIVEN** a team whose name is wider than the menu
- **WHEN** the menu opens
- **THEN** the team heading stays on one line and ends with an ellipsis
