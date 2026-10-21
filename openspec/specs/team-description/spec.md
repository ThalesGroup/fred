# team-description Specification

## Purpose
Make every team state its objectives regarding its use of AI through a required description, kept valid from creation to edit, enforced by the database, filled with a placeholder for teams that predate the rule, and shown to everyone browsing the marketplace.

## Requirements

### Requirement: A team is created with a description

Creating a team SHALL require a description. The description SHALL be stored without surrounding whitespace and SHALL count between 20 and 500 characters once trimmed. A creation request without a description, or with one outside these bounds, SHALL be refused and no team SHALL be created.

#### Scenario: Valid description
- **WHEN** a platform admin creates a team with the description "Automate the drafting of our monthly HR reports."
- **THEN** the team is created with that description

#### Scenario: Missing description
- **WHEN** a team manager creates a team without a description
- **THEN** the request is refused with a validation error
- **AND** no team is created

#### Scenario: Too short once trimmed
- **WHEN** a platform admin creates a team with the description "   Short text here   " (17 characters once trimmed)
- **THEN** the request is refused with a validation error

#### Scenario: Exactly the bounds
- **WHEN** a platform admin creates a team with a description of exactly 20 characters, and another with exactly 500 characters
- **THEN** both teams are created

#### Scenario: Too long
- **WHEN** a platform admin creates a team with a description of 501 characters
- **THEN** the request is refused with a validation error

#### Scenario: Surrounding whitespace removed
- **WHEN** a platform admin creates a team with the description "  Summarise customer tickets for the support desk.  "
- **THEN** the team's description is "Summarise customer tickets for the support desk."

### Requirement: The admin create-team form requires a description

The create-team form SHALL include a required description field with a character counter and a helper text explaining that the description states the team's objectives regarding its use of AI, in French and English. The form SHALL NOT submit while the trimmed description is shorter than 20 or longer than 500 characters.

#### Scenario: Submit disabled until valid
- **WHEN** an admin fills the team name and an initial team admin but types a 10-character description
- **THEN** the create action stays unavailable
- **AND** the field explains the 20-character minimum

#### Scenario: Valid form
- **WHEN** the admin types a 40-character description
- **THEN** the create action becomes available and sends the trimmed description

### Requirement: A team admin can edit but not clear the description

A team admin SHALL be able to change the team's description. An edit SHALL be refused when it sets the description to nothing, to a blank value, or to fewer than 20 or more than 500 characters once trimmed; the stored description SHALL stay unchanged. An accepted edit SHALL be stored trimmed. The team settings field SHALL validate the value when it loses focus, show the error on the field, and SHALL NOT send an invalid value.

#### Scenario: Valid edit
- **WHEN** a team admin changes the description to "Answer internal IT questions from our knowledge base."
- **THEN** the new description is stored

#### Scenario: Clearing refused
- **WHEN** a team admin sends an edit setting the description to null or to "   "
- **THEN** the request is refused with a validation error
- **AND** the previous description is kept

#### Scenario: Shortening below the minimum refused
- **WHEN** a team admin sends an edit setting the description to "Too short"
- **THEN** the request is refused with a validation error

#### Scenario: Settings field blocks an invalid value
- **WHEN** a team admin empties the description field in team settings and leaves it
- **THEN** the field shows an error
- **AND** no update request is sent

#### Scenario: Other fields untouched
- **WHEN** a team admin edits only the team's joining mode
- **THEN** the edit is accepted and the description is unchanged

### Requirement: The database refuses an invalid team description

The stored description of a team SHALL be required, SHALL hold at most 500 characters, and the database SHALL refuse any write whose trimmed description is shorter than 20 characters, whichever code path performs it.

#### Scenario: Direct write without description
- **WHEN** a team metadata row is inserted without a description
- **THEN** the database refuses the write

#### Scenario: Direct write with a short description
- **WHEN** a team metadata row is written with the description "Short"
- **THEN** the database refuses the write

### Requirement: Existing teams receive a placeholder description

Upgrading the database SHALL give every existing team whose description is missing, blank or shorter than 20 trimmed characters the placeholder « Description à compléter par l'administrateur de l'équipe. » before the new constraints apply. Teams with a valid description SHALL keep it, trimmed. Downgrading SHALL restore an optional description of at most 180 characters, clearing placeholder descriptions and cutting longer ones to 180 characters.

#### Scenario: Missing description backfilled
- **WHEN** the database holds a team with no description and is upgraded
- **THEN** the team's description is the placeholder

#### Scenario: Short description backfilled
- **WHEN** the database holds a team described "Ops" and is upgraded
- **THEN** the team's description is the placeholder

#### Scenario: Valid description kept
- **WHEN** the database holds a team described "  Draft and review procurement contracts.  " and is upgraded
- **THEN** the team's description is "Draft and review procurement contracts."

#### Scenario: Downgrade
- **WHEN** a database holding a placeholder description and a 300-character description is downgraded
- **THEN** the placeholder becomes empty and the long description keeps its first 180 characters

### Requirement: Imports and backfills never fail on a team description

A platform import SHALL NOT fail because a team's description is missing, blank or shorter than 20 characters: such a team SHALL receive the placeholder. This SHALL hold both for imported team metadata and for teams the import creates from its user list. A description longer than 500 characters SHALL be cut to 500. Any other tool that creates a team record without a description SHALL use the placeholder.

#### Scenario: Imported team without description
- **WHEN** a platform bundle carries a team metadata row with no description
- **THEN** the team is imported with the placeholder description

#### Scenario: Imported team with a valid description
- **WHEN** a platform bundle carries a team described "Prepare board meeting briefs and minutes."
- **THEN** the team is imported with that description

#### Scenario: Team created from the user list
- **WHEN** an import's user list references a team that does not exist yet and declares its team admin
- **THEN** the team is created with the placeholder description

#### Scenario: Storage backfill creates a team record
- **WHEN** the Knowledge Flow storage backfill finds storage for a team that has no metadata record
- **THEN** the record it creates carries the placeholder description

### Requirement: Team admins are reminded to replace the placeholder

The team returned by the API SHALL state whether its description is the placeholder. While it is, a team admin SHALL see a reminder to write the description on the team's home page and in team settings. Members without the team admin role SHALL NOT see the reminder. The reminder SHALL disappear once the description is replaced.

#### Scenario: Reminder shown to a team admin
- **WHEN** a team admin opens a team whose description is the placeholder
- **THEN** a reminder asks them to describe the team's objectives regarding AI

#### Scenario: Not shown to a member
- **WHEN** a team member who is not a team admin opens the same team
- **THEN** no reminder is shown

#### Scenario: Reminder gone after edit
- **WHEN** the team admin saves a real description
- **THEN** the team no longer reports a placeholder and the reminder disappears

#### Scenario: Settings field starts empty
- **WHEN** a team admin opens the settings of a team whose description is the placeholder
- **THEN** the description field is empty
- **AND** leaving it empty shows an error on the field and sends no update request

#### Scenario: Placeholder shown in the user's language
- **WHEN** a user whose interface is in English sees a team whose description is the placeholder
- **THEN** the description reads "Description to be completed by the team administrator." while the stored value stays the French placeholder

### Requirement: Personal spaces have no description

A user's personal space SHALL keep no description and SHALL NOT be subject to the description rules or the placeholder reminder.

#### Scenario: Personal space listed
- **WHEN** a user lists their teams
- **THEN** their personal space has no description and does not report a placeholder

### Requirement: Marketplace team cards show the description

Every team card on the marketplace teams page SHALL show the team's description, limited to three lines, both in the user's own teams and in the teams to discover.

#### Scenario: Own team card
- **WHEN** a user opens the marketplace teams page and is a member of a described team
- **THEN** that team's card in "Your teams" shows its description

#### Scenario: Discover card
- **WHEN** the page lists a public team the user is not a member of
- **THEN** its card shows its description
