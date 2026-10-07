## ADDED Requirements

### Requirement: Simple view offers two independent document packs

The Simple capabilities view SHALL offer two independent packs in its "Data and knowledge" section: "Attachments" and "Team documents". Each pack SHALL be selectable only when the team can use document access. Turning on "Attachments" SHALL select document access with attachments on. Turning on "Team documents" SHALL select document access with team documents on. Turning on one pack SHALL NOT turn on the other pack's source.

#### Scenario: Two document cards are shown

- **WHEN** a member opens the Simple capabilities view for a team that can use document access
- **THEN** the "Attachments" and "Team documents" cards are present, and no "Team resources" card or "Search in attachments only" switch is present

#### Scenario: Attachments alone

- **WHEN** a member turns on "Attachments" on an agent with no capability selected
- **THEN** document access is selected with attachments on and team documents off, and similarity search is not selected

#### Scenario: Team documents alone

- **WHEN** a member turns on "Team documents" on an agent with no capability selected
- **THEN** document access is selected with team documents on and attachments off

#### Scenario: Both packs on

- **WHEN** a member turns on both packs
- **THEN** document access is selected with both sources on

#### Scenario: Document access is unavailable

- **WHEN** the team cannot use document access
- **THEN** neither document pack is selectable

### Requirement: Turning off the last document pack deselects document access

Turning off one document pack while the other stays on SHALL turn off only that pack's source. Turning off the last active document pack SHALL deselect document access instead of saving a configuration with both sources off. The stored library scope SHALL be kept in the form so that turning "Team documents" back on restores it.

#### Scenario: Turn off one of two packs

- **WHEN** both packs are on and a member turns off "Attachments"
- **THEN** document access stays selected with attachments off and team documents on

#### Scenario: Turn off the last pack

- **WHEN** only "Team documents" is on and a member turns it off
- **THEN** document access and the capabilities owned only by the document packs are deselected, and unrelated selections remain unchanged

### Requirement: Library binding belongs to the Team documents pack

The active "Team documents" pack SHALL offer the library binding switch and folder picker. The "Attachments" pack SHALL offer no scope option.

#### Scenario: Library binding under Team documents

- **WHEN** "Team documents" is on in the Simple view
- **THEN** its card shows the library binding switch and, while binding is on, the folder picker

#### Scenario: No library option on Attachments

- **WHEN** only "Attachments" is on in the Simple view
- **THEN** no library binding option is shown

### Requirement: Document reading is granted by the document-access packs

The Simple view SHALL NOT offer a standalone pack whose only purpose is to enable verbatim document reading and exhaustive extraction. Verbatim reading, exhaustive extraction, summarization and tabular access SHALL instead be granted by the two document packs, "Attachments" and "Team documents". Each of these capabilities SHALL be selected when either pack is turned on and is available to the team. Each SHALL be withdrawn only when both packs are off.

#### Scenario: Enabling team documents grants the shared capabilities

- **WHEN** a member switches on "Team documents" on an agent with no capability selected
- **THEN** verbatim reading, exhaustive extraction, summarization and tabular access are enabled, alongside similarity search

#### Scenario: Enabling attachments grants the shared capabilities

- **WHEN** a member switches on "Attachments" on an agent with no capability selected
- **THEN** verbatim reading, exhaustive extraction, summarization and tabular access are enabled

#### Scenario: Shared capabilities survive while either pack remains on

- **WHEN** both document packs are on and the member switches one of them off
- **THEN** verbatim reading, exhaustive extraction, summarization and tabular access remain enabled

#### Scenario: Shared capabilities are withdrawn when both packs are off

- **WHEN** the member switches off the last remaining document pack
- **THEN** verbatim reading, exhaustive extraction, summarization and tabular access are no longer enabled

#### Scenario: No standalone document-reading pack is offered

- **WHEN** a member opens the Simple capabilities view
- **THEN** no pack card offers document reading on its own

### Requirement: A pack lists the capabilities it grants

Each pack SHALL display, in its expandable list of included capabilities, the backend capabilities that switching the pack on enables, each with its availability status for the team. A pack MAY omit a capability that implements the pack's own premise rather than adding a distinct ability to the agent.

#### Scenario: Team documents lists its granted capabilities

- **WHEN** a member expands the "Team documents" pack
- **THEN** the list shows document access, tabular data, summarization, similarity search, verbatim reading, and exhaustive extraction

#### Scenario: Attachments lists its granted capabilities

- **WHEN** a member expands the "Attachments" pack
- **THEN** the list shows document access, tabular data, summarization, verbatim reading, and exhaustive extraction, and does not list similarity search

#### Scenario: A capability the platform admin has not enabled is marked unavailable

- **WHEN** a pack grants a capability that the platform administrator has not enabled for the team
- **THEN** that capability is shown as unavailable in the pack's list, and switching the pack on does not enable it

### Requirement: Pack state reflects the stored capability selection

A pack's on/off state SHALL be derived from the agent's stored capability selection rather than held separately, so the Simple and Advanced views cannot disagree. A document pack SHALL be on when document access is selected and the pack's own source is on. Each source SHALL be read after the legacy compatibility mapping of the `document-access-sources` capability is applied. A document pack's state SHALL NOT depend on the capabilities it shares with the other pack. Toggling a pack SHALL leave every capability the pack does not grant untouched.

#### Scenario: Clearing document access in the Advanced view turns the packs off

- **WHEN** a member clears the document-access capability in the Advanced view and returns to the Simple view
- **THEN** both document packs are shown as off

#### Scenario: Clearing a shared capability leaves the pack on

- **WHEN** a member clears only summarization or a reading capability in the Advanced view, leaving document access on
- **THEN** the pack stays on, and that capability is shown in the pack's list as available but not active

#### Scenario: Legacy agent shows its mapped sources

- **WHEN** the form opens an agent whose stored document access still uses `show_attach_files_control` on and `search_attachments_only` on
- **THEN** "Attachments" is shown on and "Team documents" is shown off, without rewriting the stored selection

#### Scenario: Toggling a pack preserves unrelated capabilities

- **WHEN** a member switches a pack on or off
- **THEN** capabilities granted by no pack, or granted only by other packs that remain on, keep their previous state

## MODIFIED Requirements

### Requirement: Similarity search stays scoped to the team corpus

Similarity search SHALL be granted only by the "Team documents" pack. The Simple view SHALL NOT grant it through the "Attachments" pack, because similarity search does not cover the files attached to a conversation. Turning off "Team documents" SHALL withdraw similarity search even while "Attachments" stays on.

#### Scenario: Attachments-only agent does not get similarity search

- **WHEN** a member switches on "Attachments" while "Team documents" is off
- **THEN** similarity search is not enabled on that agent

#### Scenario: Turning off team documents withdraws similarity

- **WHEN** both packs are on and a member switches off "Team documents"
- **THEN** similarity search is withdrawn and the shared capabilities remain enabled

### Requirement: Advanced document choices stay independent

Advanced SHALL let a member select document access and switch each source without implicitly enabling any other capability. The document access card SHALL show the "Attachments" and "Team documents" switches before its other settings. Scope pickers and library binding SHALL be shown only while "Team documents" is on. While document access is selected with both sources off, the card SHALL show a save-blocking error that asks the member to turn on a source or deselect the capability. Saving SHALL stay blocked until this is resolved. Stored selections SHALL NOT be rewritten on form load or on an unrelated save.

#### Scenario: Select attachments only in Advanced

- **WHEN** a member turns off "Team documents" on the document access card in Advanced
- **THEN** no capability is added or removed, the scope pickers and library binding are hidden, and the Simple "Team documents" pack reads off

#### Scenario: Both sources off blocks saving

- **WHEN** a member turns off both sources on the Advanced document access card while the capability stays selected
- **THEN** the card shows a save-blocking error asking the member to turn on a source or deselect the capability, and the form cannot be saved until one of these is done

#### Scenario: Existing corpus-only agent keeps its selection

- **WHEN** the form opens or saves an unrelated edit to an agent whose legacy configuration had the paperclip off
- **THEN** attachments stay off, team documents stay on, and the selected capabilities remain unchanged

#### Scenario: Disable attachments in Advanced

- **WHEN** a member keeps "Team documents" on but turns off "Attachments" on the Advanced document access card
- **THEN** attachments stay off after saving and on later edits, and the Simple "Attachments" pack reads off

#### Scenario: Existing attachment-only agent keeps its selection

- **WHEN** the form opens an agent stored in the former attachments-only mode
- **THEN** its selected capabilities remain unchanged, "Attachments" reads on and "Team documents" reads off

#### Scenario: Explicit Simple activation replaces a partial selection

- **WHEN** a member turns on a document pack in Simple while the agent has only a partial Advanced or legacy selection
- **THEN** the pack's available members are selected and its source is turned on

## REMOVED Requirements

### Requirement: One Simple pack grants the resource and attachment bundle

**Reason**: Members could not express "attachments only" without first enabling the team corpus and then restricting it. Each document source now has its own Simple pack backed by a positive `document_access` setting.

**Migration**: Use the "Attachments" and "Team documents" packs. Existing agents keep their stored selection, and their legacy settings are read through the `document-access-sources` compatibility mapping.

### Requirement: Simple pack can restrict search to attachments

**Reason**: The negative "Search in attachments only" switch is replaced by turning off the "Team documents" pack.

**Migration**: An agent stored with `search_attachments_only` on reads with "Attachments" on and "Team documents" off. The next save writes `attachments=true, team_documents=false`.

### Requirement: Document reading is granted by the Team resources pack

**Reason**: The single "Team resources" pack is split into "Attachments" and "Team documents".

**Migration**: Use "Document reading is granted by the document-access packs".

### Requirement: Each pack lists the capabilities it grants

**Reason**: Its scenarios name the retired "Team resources" pack.

**Migration**: Use "A pack lists the capabilities it grants".

### Requirement: Pack state follows the stored capability selection

**Reason**: Each document pack's state now comes from document access plus its own source.

**Migration**: Use "Pack state reflects the stored capability selection".
