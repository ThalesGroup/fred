## Purpose

A team prompt can carry a short command that identifies it for invocation from
the chat composer. This capability defines the command's accepted form, its
uniqueness within a team, and how it behaves when a prompt is published or
imported by another team.

## ADDED Requirements

### Requirement: A prompt MAY carry a command

A team prompt SHALL accept an optional command, distinct from its name. A
prompt without a command SHALL remain fully usable through every surface that
does not need one.

#### Scenario: Prompt created with a command

- **WHEN** a prompt is created with the command `summary`
- **THEN** the prompt is stored with that command
- **AND** reading the prompt returns it

#### Scenario: Prompt created without a command

- **WHEN** a prompt is created with no command
- **THEN** the prompt is stored with an empty command
- **AND** it is listed and readable exactly as a prompt with one

#### Scenario: Command removed from an existing prompt

- **WHEN** a prompt that has the command `summary` is updated with no command
- **THEN** the prompt keeps its name, text and every other attribute
- **AND** `summary` becomes available for another prompt in that team

### Requirement: A command SHALL be a lowercase unaccented slug

A command SHALL contain only lowercase ASCII letters, digits, the hyphen `-`
and the underscore `_`, and SHALL be at most 64 characters long. It SHALL NOT
contain whitespace, accented characters, or any other punctuation. Input that
does not conform SHALL be rejected by the API with a validation error naming
the field; it SHALL NOT be silently normalised server-side.

The editing surface SHALL prevent disallowed characters from being entered at
all, rather than accepting them and failing on save. An uppercase letter is
folded to lowercase as it is typed — a visible, immediate transformation, not
a silent server-side rewrite — and every other disallowed character is
refused by the input.

#### Scenario: Accented command rejected

- **WHEN** a prompt is created with the command `résumé`
- **THEN** the request is rejected with a validation error identifying the
  command field
- **AND** no prompt is created

#### Scenario: Command containing whitespace rejected

- **WHEN** a prompt is created with the command `mon resume`
- **THEN** the request is rejected with a validation error identifying the
  command field

#### Scenario: Uppercase rejected by the API

- **WHEN** a create request carries the command `Summary`
- **THEN** the request is rejected with a validation error
- **AND** no prompt is created with the command `summary`

#### Scenario: Digits, hyphens and underscores accepted

- **WHEN** a prompt is created with the command `synthese_v2-bis`
- **THEN** the prompt is created with that command

#### Scenario: Over-long command rejected

- **WHEN** a prompt is created with a command of 65 characters
- **THEN** the request is rejected with a validation error identifying the
  command field

#### Scenario: The input folds an uppercase keystroke

- **WHEN** the user types `S` into the command field
- **THEN** the field shows `s`

#### Scenario: The input refuses a disallowed character

- **WHEN** the user types a space, an accented letter or a punctuation mark
  into the command field
- **THEN** the field's value is unchanged

### Requirement: A command SHALL be unique within its team

Two prompts of one team SHALL NOT hold the same command. Uniqueness SHALL be
guaranteed by storage, not only checked by the application, so concurrent
writes cannot produce a duplicate.

An attempt to create or update a prompt with a command already held by another
prompt of that team SHALL be refused with a conflict distinguishable from a
name conflict, so the editing surface can point at the right field.

The same command MAY be held by prompts of different teams: a command is
team-local.

#### Scenario: Duplicate command within a team refused

- **GIVEN** a prompt in team A holds the command `summary`
- **WHEN** another prompt in team A is created with the command `summary`
- **THEN** the request is refused with a conflict naming the command field
- **AND** the existing prompt is unchanged

#### Scenario: Same command in two teams allowed

- **GIVEN** a prompt in team A holds the command `summary`
- **WHEN** a prompt in team B is created with the command `summary`
- **THEN** the prompt in team B is created

#### Scenario: Updating a prompt keeps its own command

- **GIVEN** a prompt holds the command `summary`
- **WHEN** that same prompt is updated with the command `summary` and a new
  text
- **THEN** the update succeeds
- **AND** the command is unchanged

#### Scenario: Command conflict is distinguishable from a name conflict

- **WHEN** a create request conflicts on the command only
- **THEN** the error identifies the command as the conflicting field
- **AND** it is not reported as a duplicate name

### Requirement: An import SHALL carry the command, suffixed on collision

Importing a published prompt SHALL copy its command: it is what the author
intended, and dropping it loses information the destination team may want.
Marketplace payloads SHALL therefore expose the command, because the import
reads it from them.

An import SHALL NOT be refused because of a command: where the destination
team already holds it, the copy SHALL take the first free `-N` variant,
starting at `-2` and counting up — the same treatment the prompt's name
already receives. The base SHALL be shortened where needed so the suffixed
command still satisfies the length limit.

Choosing destinations SHALL therefore be unaffected by commands: every team
the caller may import into is offered, whatever commands it already holds.

#### Scenario: Marketplace payload carries the command

- **GIVEN** a published prompt whose author team gave it the command `summary`
- **WHEN** it is read through a marketplace surface
- **THEN** the payload carries `summary`

#### Scenario: Import into a team where the command is free

- **GIVEN** no prompt in team B holds `summary`
- **WHEN** team B imports a published prompt whose command is `summary`
- **THEN** the imported prompt holds `summary`

#### Scenario: Import into a team that already holds the command

- **GIVEN** a prompt in team B holds `summary`
- **WHEN** team B imports a published prompt whose command is `summary`
- **THEN** the import succeeds
- **AND** the imported prompt holds `summary-2`
- **AND** the existing prompt keeps `summary`

#### Scenario: Suffix counts up past an existing variant

- **GIVEN** prompts in team B hold `summary` and `summary-2`
- **WHEN** team B imports a published prompt whose command is `summary`
- **THEN** the imported prompt holds `summary-3`

#### Scenario: Import of a prompt with no command

- **WHEN** a published prompt with no command is imported
- **THEN** the imported prompt has no command
- **AND** no suffix is invented for it

#### Scenario: A team holding the command is still a valid destination

- **GIVEN** team B holds `summary` and team C does not
- **WHEN** a published prompt whose command is `summary` is imported into both
- **THEN** both imports succeed
- **AND** neither team was withheld from the destination picker

#### Scenario: The author's team reads as already holding the prompt

- **WHEN** the destination picker is opened
- **THEN** the prompt's own team is shown selected and not selectable
- **AND** it is not submitted as an import target

### Requirement: Commands SHALL be reserved within one namespace per team

The command namespace SHALL be one per team, shared with any future
team-scoped invocable object. A command accepted today SHALL NOT need renaming
when a second kind of invocable object is introduced in that team; such an
object SHALL be refused a command a prompt of that team already holds.

#### Scenario: Reservation holds for a later kind of invocable object

- **GIVEN** a prompt in team A holds the command `summary`
- **WHEN** a second kind of team-scoped invocable object is later introduced in
  team A
- **THEN** it cannot take the command `summary` while that prompt holds it
- **AND** the prompt's command remains valid and unchanged
