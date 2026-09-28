## ADDED Requirements

### Requirement: A command menu SHALL open on `/` at the start of an empty composer

Typing `/` as the first character of an otherwise empty composer SHALL open a
command menu above it. The menu SHALL NOT open for a `/` typed anywhere else,
so ordinary text containing a slash never triggers it.

Characters typed after the `/` SHALL filter the menu. Deleting back past the
`/` SHALL close it.

#### Scenario: The trigger fires at the start of an empty composer

- **WHEN** the user types `/` into an empty composer
- **THEN** the command menu opens above the composer

#### Scenario: A slash inside text does not trigger

- **GIVEN** the composer contains `cat /tmp`
- **WHEN** the user has typed the `/`
- **THEN** no menu opens

#### Scenario: Typing filters the menu

- **GIVEN** the menu is open and the team has commands `summary` and `search`
- **WHEN** the user types `su`
- **THEN** only `summary` is offered

#### Scenario: Deleting the trigger closes the menu

- **GIVEN** the menu is open on `/su`
- **WHEN** the user deletes back past the `/`
- **THEN** the menu closes

### Requirement: The menu SHALL be a sectioned list

The menu SHALL render its entries under section headings rather than as one
flat list, with a single section today titled for the team's prompt library.
The heading SHALL render even when it is the only section, so introducing a
second kind of invocable object is a new entry and not a visual change.

Only prompts of the active team that carry a command SHALL be offered, and
**every** one of them SHALL be, whatever the size of the team's library: a
command the menu cannot see is also a command submit cannot resolve, and an
unresolved token is sent to the agent as ordinary text.

#### Scenario: The single section is titled

- **WHEN** the menu opens
- **THEN** its entries appear under a heading naming the prompt library

#### Scenario: A large library still offers every command

- **GIVEN** a team holding more prompts than one page of its library lists
- **WHEN** the menu opens
- **THEN** a command held by a prompt outside that page is still offered
- **AND** submitting it runs the prompt rather than sending the token as text

#### Scenario: Prompts without a command are not offered

- **GIVEN** the team has prompts with and without commands
- **WHEN** the menu opens
- **THEN** only those carrying a command are listed

### Requirement: The menu SHALL say when it has nothing to offer

When the trigger is live but no entry can be offered, the menu SHALL show why
rather than not appearing: the composer's placeholder has just invited the user
to type `/`, so a silent nothing reads as a broken hint. It SHALL distinguish a
team that holds no command at all from a query matching none of the ones it
holds.

Such a panel SHALL claim no key but `Esc`: the typed token SHALL still submit as
ordinary text, and `Tab` SHALL still move focus.

#### Scenario: A team with no command says so

- **GIVEN** the active team holds no prompt carrying a command
- **WHEN** the user types `/`
- **THEN** the menu says the team holds no command

#### Scenario: A query matching nothing says something else

- **GIVEN** the team holds commands and the user types `/zzz`
- **WHEN** no command matches
- **THEN** the menu says no command matches

#### Scenario: An empty menu does not swallow the send

- **GIVEN** the menu is showing that nothing matches `/zzz`
- **WHEN** the user submits
- **THEN** `/zzz` is sent as ordinary text

### Requirement: The menu SHALL be fully operable from the keyboard

The menu SHALL open with its best match focused. `Down` and `Up` SHALL move
the focus to the next and previous entry in visual order, crossing section
boundaries as if the list were flat, and wrapping at either end. Continuing to
type SHALL re-filter and re-focus the best match, so the focus is never left
on something the user cannot see.

`Tab` SHALL complete the focused command into the composer, close the menu,
and append a trailing space. `Enter` SHALL run the focused command. `Esc`
SHALL close the menu and leave the typed text untouched. Activating an entry
with a pointer SHALL behave as `Tab`.

Focus SHALL remain in the composer throughout: the menu is a list the text
field owns and points at, which is what frees `Tab` to mean "complete". Since
`Tab` cannot move focus while the menu is open, `Esc` SHALL always close it —
the menu SHALL NOT be dismissable by pointer alone.

The menu belongs to the focused composer: it SHALL close when the composer
loses focus and SHALL come back when focus returns, unless `Esc` closed it.
A pointer activation SHALL NOT count as losing focus.

The focused entry SHALL be conveyed to assistive technology without moving
focus out of the composer.

#### Scenario: Arrows walk every entry and wrap

- **GIVEN** the menu lists three commands with the first focused
- **WHEN** the user presses `Up`
- **THEN** the third is focused

#### Scenario: Tab completes without running

- **GIVEN** the menu is open with `summary` focused
- **WHEN** the user presses `Tab`
- **THEN** the composer contains `/summary ` with a trailing space
- **AND** the menu closes
- **AND** nothing is sent

#### Scenario: Enter runs the focused command

- **GIVEN** the menu is open with `summary` focused
- **WHEN** the user presses `Enter`
- **THEN** the command runs

#### Scenario: Esc closes and keeps what was typed

- **GIVEN** the composer contains `/su` with the menu open
- **WHEN** the user presses `Esc`
- **THEN** the menu closes
- **AND** the composer still contains `/su`

#### Scenario: A pointer activation behaves as Tab

- **WHEN** the user activates an entry with a pointer
- **THEN** the composer contains that command with a trailing space
- **AND** nothing is sent

#### Scenario: Losing focus closes the menu, regaining it brings it back

- **GIVEN** the menu is open on `/su`
- **WHEN** the composer loses focus
- **THEN** the menu closes
- **AND** it opens again on the same entries when focus returns

#### Scenario: Esc outlives a focus round trip

- **GIVEN** `Esc` closed the menu on `/su`
- **WHEN** the composer loses and regains focus
- **THEN** the menu stays closed

#### Scenario: The caret never leaves the composer

- **WHEN** the menu is open and the user moves the focus through it
- **THEN** the composer keeps the caret
- **AND** the focused entry is conveyed to assistive technology

### Requirement: Running a command SHALL send the prompt, not the command

Running a command SHALL send the text of the prompt behind it. That text SHALL
NOT appear in the composer at any point, and the literal command SHALL NOT be
sent as the turn's content.

Text typed after the command SHALL be appended to the prompt's text. It is
free-text continuation: it SHALL NOT be parsed, named or validated.

The turn SHALL carry the command descriptor, so the transcript renders it as
its command.

A completed command in the composer SHALL run on submit even when the menu is
already closed, so completing with `Tab` then pressing `Enter` reaches the
same place as `Enter` alone.

#### Scenario: The prompt is sent, never shown in the composer

- **GIVEN** a prompt whose command is `summary`
- **WHEN** the user runs it
- **THEN** the turn's content is the prompt's text
- **AND** the prompt's text never appeared in the composer

#### Scenario: Trailing text is appended

- **GIVEN** a prompt whose command is `summary` and whose text ends in a colon
- **WHEN** the user runs `/summary 33 lignes`
- **THEN** the turn's content is the prompt's text followed by `33 lignes`
- **AND** the descriptor records `33 lignes` as the appended text

#### Scenario: Submit runs a completed command with the menu closed

- **GIVEN** the composer contains `/summary ` and the menu is closed
- **WHEN** the user submits
- **THEN** the command runs
- **AND** the literal text `/summary` is not sent

#### Scenario: An unknown command is sent as ordinary text

- **GIVEN** the composer contains `/nosuchcommand` and no prompt holds it
- **WHEN** the user submits
- **THEN** the text is sent as typed
- **AND** the turn carries no command descriptor

### Requirement: The trigger SHALL be discoverable

The composer SHALL show a placeholder whenever it is empty, whether or not it
has focus, naming both what the field is for and the `/` trigger. It SHALL
disappear only once the user has typed something.

A placeholder is not an accessible instruction — it is not reliably announced
and it vanishes on the first keystroke — so the same hint SHALL also be
carried by the field's accessible description.

The Help Center SHALL document the feature in `fr` and `en` in this change.

#### Scenario: The hint is there before the user does anything

- **WHEN** a conversation is opened and the composer is empty
- **THEN** the placeholder names both asking a question and typing `/`
- **AND** it is shown whether or not the composer has focus

#### Scenario: The hint goes away once typing starts

- **WHEN** the user types any character
- **THEN** the placeholder is no longer shown

#### Scenario: The hint reaches assistive technology

- **WHEN** the composer is examined by assistive technology
- **THEN** the same hint is available on its accessible description
