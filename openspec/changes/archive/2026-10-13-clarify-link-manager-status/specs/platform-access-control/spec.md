## ADDED Requirements

### Requirement: Optional invitation notes have no placeholder identity

An invitation without a note SHALL have an empty note cell in history and a generic localized joiner-dialog title. An invitation with a note SHALL retain that note in history and use it to identify the joiner dialog.

#### Scenario: Invitation without a note

- **WHEN** an administrator views an invitation whose optional note is absent
- **THEN** its note cell SHALL be empty
- **AND** its joiner dialog SHALL use a generic title without a placeholder note

#### Scenario: Invitation with a note

- **WHEN** an administrator opens the joiner history for an invitation with a note
- **THEN** the note SHALL remain visible in the invitation row and joiner-dialog title

## MODIFIED Requirements

### Requirement: Administrators filter invitation history by lifecycle status

Platform administrators SHALL be able to filter one team's complete invitation history by All, Active, Revoked or Expired. All SHALL be the default. Results and pagination totals SHALL reflect the selected status across the entire history, not only loaded rows. Revoked SHALL take precedence over Expired, which SHALL take precedence over Suspended; unrevoked, unexpired links SHALL be Active when Link access is enabled and Suspended otherwise. Changing the filter SHALL start at the first page and SHALL NOT display rows from the previous filter as current results. Filtering SHALL NOT change validity, membership, counters or access settings. The history table SHALL have a bounded fixed height with internal row scrolling, while its header, pagination and surrounding controls remain visible. When Link access is disabled, the invitation manager SHALL state that link sharing is disabled and valid links are suspended until it is enabled again.

#### Scenario: Filter beyond the first page

- **WHEN** an administrator selects Expired and matching links exist beyond the previously loaded page
- **THEN** the result pages and total SHALL include all and only expired links for the selected team

#### Scenario: Revoked link also expires

- **WHEN** an expired link has been revoked
- **THEN** it SHALL appear under Revoked and All, not under Expired

#### Scenario: Link access is disabled

- **WHEN** a team's Link access is disabled
- **THEN** its unrevoked, unexpired links SHALL appear in All with grayscale rows at reduced opacity, rather than appearing under Active
- **AND** those rows SHALL display Suspended in the visible Status column
- **AND** the manager SHALL explain that Link access is disabled and valid invitations cannot be used until it is enabled again
- **AND** no separate Suspended filter SHALL be offered, while copying, revocation and an accessible status remain available

#### Scenario: Another administrator changes Link access

- **WHEN** the Link access setting changes while an administrator keeps the invitation manager open
- **THEN** the manager SHALL refresh the setting so its disabled notice and creation controls match the current team state
