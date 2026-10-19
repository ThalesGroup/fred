## MODIFIED Requirements

### Requirement: The user is asked once per import

The system SHALL present all conflicts of one import as a single decision point
and SHALL NOT interrupt the user once per conflicting file. Knowledge-flow imports
SHALL offer overwrite-all, skip-all, or a per-file choice. Manager original-storage
imports SHALL support skipping conflicts and SHALL keep replacement visibly
unavailable; they SHALL never imply that overwrite was performed.

#### Scenario: Ten conflicts in one import
- **WHEN** 10 of 50 selected files conflict
- **THEN** the user is asked once, with the 10 names listed
- **AND** the 40 non-conflicting files are not blocked by that decision

#### Scenario: A manager import contains existing names
- **WHEN** files conflict with names in their manager destination folder
- **THEN** the existing conflict presentation identifies those files and offers skipping them
- **AND** no replacement request or implicit overwrite occurs

### Requirement: Overwrite preserves the document identity

In the knowledge-flow replacement workflow, when the user chooses to overwrite,
the system SHALL replace the content of the existing document and SHALL preserve
its `document_uid`. It SHALL NOT create a second document, and SHALL NOT leave the
previous content indexed. Manager's original-storage workflow SHALL reject an
overwrite request as unsupported and preserve the existing document and bytes.

#### Scenario: A cited document is overwritten
- **WHEN** a document referenced by an existing agent answer is overwritten through knowledge-flow
- **THEN** that reference still resolves
- **AND** it resolves to the new content

#### Scenario: Re-indexing follows an overwrite
- **WHEN** a document is overwritten through knowledge-flow
- **THEN** its previous extracted content and vectors are replaced by the new ones
- **AND** a search no longer returns the previous content

#### Scenario: Quota reflects the difference only
- **WHEN** a 2 MB document is overwritten by a 3 MB file through knowledge-flow
- **THEN** the team's storage usage increases by 1 MB, not by 3 MB

#### Scenario: Manager receives an overwrite request
- **WHEN** a manager caller attempts to replace an existing original
- **THEN** the request is refused and the existing identity, placement, bytes and quota charge remain unchanged

### Requirement: A conflict appearing after the check is not resolved silently

The pre-check is an optimisation, not a guarantee. The system SHALL re-check at
write time and SHALL identify a newly conflicting filename explicitly, without
an overwrite. Knowledge-flow imports SHALL return the file as a conflict still
to be resolved. Manager creation-only uploads SHALL return an explicit name
conflict and retain its named refusal in the import panel until dismissed or
resolved by a deliberate new selection.

#### Scenario: A teammate imports the same name concurrently
- **WHEN** a teammate imports the same name between a knowledge-flow check and write
- **THEN** the file is returned as a conflict to resolve
- **AND** it is neither silently overwritten nor reported as a generic failure

#### Scenario: A manager reservation loses the name race
- **WHEN** a concurrent manager upload claims the same canonical folder/name after preflight
- **THEN** the losing upload reports a name conflict and preserves the winner's identity and bytes
- **AND** the panel names the refused file without sending a replacement
