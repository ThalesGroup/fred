# agent-capability-packs Specification

## Purpose
Defines the capability packs offered by the agent form's Simple view: which
packs a team member can switch on, which backend capabilities each one grants,
and how a pack's displayed state is derived from the agent's stored capability
selection so the Simple and Advanced views never disagree.

## Requirements

### Requirement: Similarity search stays scoped to the team corpus

Similarity search SHALL be granted only while the "Team resources" pack
searches the team corpus. The Simple view SHALL withdraw it in attachments-only
mode, because similarity search does not cover the files attached to a
conversation and would return no result for them.

#### Scenario: Attachments-only agent does not get similarity search

- **WHEN** a member selects attachments-only search in the active "Team
  resources" pack
- **THEN** similarity search is not enabled on that agent

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

### Requirement: Simple pack can restrict search to attachments

The active Team resources pack SHALL offer an attachments-only switch below library scoping. Selecting it SHALL keep attachment upload and admin-available shared reading capabilities active, disable corpus search in document access, and retain an admin-available tabular capability and withdraw similarity. Clearing it SHALL restore corpus search and reselect similarity when admin-available. Library scoping values SHALL remain stored across this switch.

#### Scenario: Restrict an active pack to attachments

- **WHEN** a member selects attachments-only search in the Simple Team resources pack
- **THEN** the pack remains on, document access searches only conversation attachments, tabular remains selected when available and similarity is withdrawn, and admin-available shared reading capabilities remain selected

#### Scenario: Restore corpus search

- **WHEN** a member clears attachments-only search in the Simple Team resources pack
- **THEN** the pack remains on, document access searches both sources, admin-available tabular and similarity capabilities are selected, and the saved library scope is retained

### Requirement: Advanced document choices stay independent

Advanced SHALL allow a member to select document access and its attachment and corpus options without implicitly enabling the full Simple resource bundle. The combined pack SHALL read on only when attachment upload and document access are selected and all admin-available members for the selected Simple profile are selected. In attachments-only mode, similarity SHALL be absent. Existing attachment-only selections without tabular SHALL remain unchanged until the member uses a Simple switch. Its included-capability statuses SHALL reflect the actual stored selection.

#### Scenario: Select attachments only in Advanced

- **WHEN** a member configures document access for attachments only in Advanced
- **THEN** conversation attachments are available, corpus search remains disabled, corpus-only capabilities are not added, and the combined Simple pack reads off if its shared members are incomplete

#### Scenario: Disable attachments in Advanced

- **WHEN** a member keeps corpus access but disables conversation attachments in Advanced
- **THEN** attachments remain disabled after saving and on later edits, while the combined Simple pack reads off

#### Scenario: Existing attachment-only agent keeps its selection

- **WHEN** the new frontend opens an agent that used only the former attachments pack
- **THEN** its attachments-only mode and selected capabilities remain unchanged, the combined pack reads on when its former pack members are complete, the attachments-only switch reflects the stored mode, and its selected members appear active in the included list

#### Scenario: Existing corpus-only agent keeps its selection

- **WHEN** the new frontend opens or saves an unrelated edit to a corpus-only agent
- **THEN** attachments remain disabled and the selected corpus capabilities remain unchanged

#### Scenario: Explicit Simple activation replaces a partial selection

- **WHEN** a member enables the combined pack in Simple while an agent has only a partial Advanced or legacy selection
- **THEN** the full available bundle is selected and document access is configured for both corpus and attachments

### Requirement: Document reading is granted by the Team resources pack

The Simple view SHALL NOT offer a standalone pack whose only purpose is to
enable verbatim document reading and exhaustive extraction. Both capabilities
SHALL instead be granted by the "Team resources" pack, which also covers
conversation attachments, and SHALL stay enabled while that pack is on,
including in attachments-only mode.

#### Scenario: Enabling team resources grants the reading capabilities

- **WHEN** a member switches on "Team resources" on an agent with no capability
  selected
- **THEN** verbatim reading and exhaustive extraction are enabled on that agent,
  alongside the pack's other capabilities

#### Scenario: Reading survives attachments-only search

- **WHEN** a member selects attachments-only search in the active "Team
  resources" pack
- **THEN** verbatim reading and exhaustive extraction remain enabled

#### Scenario: No standalone document-reading pack is offered

- **WHEN** a member opens the Simple capabilities view
- **THEN** no pack card offers document reading on its own

### Requirement: Each pack lists the capabilities it grants

Each pack SHALL display, in its expandable list of included capabilities, the
backend capabilities that switching the pack on enables, each with its
availability status for the team.

#### Scenario: Team resources lists its granted capabilities

- **WHEN** a member expands the "Team resources" pack
- **THEN** the list shows document access, tabular data, summarization,
  similarity search, verbatim reading, and exhaustive extraction

#### Scenario: A capability the platform admin has not enabled is marked unavailable

- **WHEN** a pack grants a capability that the platform administrator has not
  enabled for the team
- **THEN** that capability is shown as unavailable in the pack's list, and
  switching the pack on does not enable it

### Requirement: Pack state follows the stored capability selection

A pack's on/off state SHALL be derived from the agent's stored capability
selection rather than held separately, so the Simple and Advanced views cannot
disagree. Toggling a pack SHALL leave every capability the pack does not grant
untouched.

#### Scenario: Clearing document access in the Advanced view turns the pack off

- **WHEN** a member clears the document-access capability in the Advanced view
  and returns to the Simple view
- **THEN** the "Team resources" pack is shown as off

#### Scenario: Toggling a pack preserves unrelated capabilities

- **WHEN** a member switches a pack on or off
- **THEN** capabilities granted by no pack keep their previous state
