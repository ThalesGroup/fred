## Purpose

Defines the Simple agent form's capability packs, their relationship to the stored capability selection, and the boundary between bundled Simple actions and independent Advanced settings.

## ADDED Requirements

### Requirement: One Simple pack grants the resource and attachment bundle

The Simple capabilities view SHALL offer one "Team resources" pack that retains its existing corpus capabilities and includes the capabilities formerly granted by "Conversation attachments". It SHALL NOT offer a standalone attachments pack. Enabling the combined pack SHALL select every admin-available capability in that union and SHALL configure document access for both corpus search and conversation attachments.

#### Scenario: Enable the combined pack

- **WHEN** a member enables "Team resources" in Simple for an agent whose team can use document access
- **THEN** available corpus, tabular, similarity, summarization, verbatim reading, and extraction capabilities are selected, and document access allows corpus search and conversation attachments

#### Scenario: One resource card is shown

- **WHEN** a member opens the Simple capabilities view
- **THEN** the "Team resources" card is present and no separate "Conversation attachments" card is present

#### Scenario: Admin availability limits the bundle

- **WHEN** the team cannot use one included capability other than document access
- **THEN** enabling the pack skips that capability, marks it unavailable in the included list, and still enables the other available members

#### Scenario: Document access is unavailable

- **WHEN** the team cannot use document access
- **THEN** the combined resource pack is not selectable

#### Scenario: Disable the combined pack

- **WHEN** a member disables the combined pack in Simple
- **THEN** its owned capabilities are withdrawn and unrelated selections remain unchanged

### Requirement: Advanced document choices stay independent

Advanced SHALL allow a member to select document access and its attachment and corpus options without implicitly enabling the full Simple resource bundle. The combined pack SHALL read on only when document access is selected, corpus search and attachments are both enabled, and every admin-available member capability is selected. Its included-capability statuses SHALL reflect the actual stored selection.

#### Scenario: Select attachments only in Advanced

- **WHEN** a member configures document access for attachments only in Advanced
- **THEN** conversation attachments are available, corpus search remains disabled, corpus-only capabilities are not added, and the combined Simple pack reads off

#### Scenario: Disable attachments in Advanced

- **WHEN** a member keeps corpus access but disables conversation attachments in Advanced
- **THEN** attachments remain disabled after saving and on later edits, while the combined Simple pack reads off

#### Scenario: Existing attachment-only agent keeps its selection

- **WHEN** the new frontend opens an agent that used only the former attachments pack
- **THEN** its attachments-only mode and selected capabilities remain unchanged, the combined pack reads off, and its selected members appear active in the included list

#### Scenario: Existing corpus-only agent keeps its selection

- **WHEN** the new frontend opens or saves an unrelated edit to a corpus-only agent
- **THEN** attachments remain disabled and the selected corpus capabilities remain unchanged

#### Scenario: Explicit Simple activation replaces a partial selection

- **WHEN** a member enables the combined pack in Simple while an agent has only a partial Advanced or legacy selection
- **THEN** the full available bundle is selected and document access is configured for both corpus and attachments
