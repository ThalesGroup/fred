## ADDED Requirements

### Requirement: A user can mark a library prompt as a favorite

The system SHALL let any user who can read a prompt, in a team library or in their personal space, mark it as a favorite and unmark it. Favorites SHALL be personal: one user's favorites SHALL NOT be visible to anyone else. Marking and unmarking SHALL be idempotent.

#### Scenario: Marking a prompt from its tile

- **WHEN** a user activates the star on a prompt tile that is not a favorite
- **THEN** the prompt becomes a favorite for that user
- **AND** the star shows filled in the warning colour, and its accessible state is pressed

#### Scenario: Unmarking a prompt

- **WHEN** a user activates the filled star of a favorite prompt
- **THEN** the prompt is no longer a favorite for that user
- **AND** the star shows as an outline

#### Scenario: A read-only member

- **WHEN** a member who can read but not edit a team's prompts activates the star
- **THEN** the prompt becomes a favorite for them

#### Scenario: Another user's view

- **WHEN** a user has marked a team prompt as a favorite
- **THEN** another member of the team sees that prompt with an outline star

#### Scenario: The toggle fails

- **WHEN** the server rejects a favorite change
- **THEN** the star returns to its previous state and the user is told the change failed

### Requirement: Favorites can be filtered in the Prompts page and the chat panel

The Prompts page and the chat's prompt panel SHALL offer a Favorites filter that is always visible, in both the Team and My space contexts. It SHALL combine with the category filter: only prompts that are favorites and match the selected category are shown. When nothing matches, the system SHALL say so and how to add a favorite.

#### Scenario: Favorites only

- **WHEN** a user activates the Favorites filter with no category selected
- **THEN** only their favorite prompts of the current library are listed

#### Scenario: Favorites within a category

- **WHEN** a user activates the Favorites filter and selects a category
- **THEN** only their favorite prompts of that category are listed

#### Scenario: A library without categories

- **WHEN** a library has no categories
- **THEN** the Favorites filter is still shown

#### Scenario: No favorites

- **WHEN** the Favorites filter is active and nothing matches
- **THEN** an empty state explains that starring a prompt adds it there

#### Scenario: Active and inactive appearance

- **WHEN** the Favorites filter is inactive
- **THEN** it shows a filled star in the warning colour on a neutral chip
- **WHEN** it is active
- **THEN** the chip fills with the warning colour and its star and label use the on-warning colour

### Requirement: Favorites do not outlive what they point to

The system SHALL remove a favorite when its prompt is deleted, when its user leaves or is removed from the prompt's team, and when its user's account is deleted.

#### Scenario: Prompt deleted

- **WHEN** a prompt that users marked as a favorite is deleted
- **THEN** no favorite refers to it any more

#### Scenario: Leaving a team

- **WHEN** a user leaves or is removed from a team
- **THEN** their favorites on that team's prompts are deleted
- **AND** their favorites on other teams' prompts and in their personal space remain

#### Scenario: Account deleted

- **WHEN** a user's account is deleted
- **THEN** all of their favorites are deleted
