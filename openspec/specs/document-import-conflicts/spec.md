# document-import-conflicts Specification

## Purpose
Detect, before any file content is uploaded, that a document of the same name
already exists in the destination folder, let the user decide once for the whole
import, and apply that decision without losing the existing document's identity.

## Requirements

### Requirement: Conflicts are detected before content is uploaded

The system SHALL expose a check that, given a destination folder and a list of
file names, returns which of those names already identify a document in that
folder. The check SHALL NOT require the file content.

#### Scenario: Some names already exist

- **WHEN** a user selects 50 files for a folder already holding 10 of those names
- **THEN** the check returns exactly those 10 names
- **AND** no file content has been transmitted

#### Scenario: No name exists

- **WHEN** none of the selected names exist in the destination folder
- **THEN** the check returns an empty list
- **AND** the import proceeds without asking the user anything

#### Scenario: The check is scoped to one folder

- **WHEN** a document of the same name exists only in a different folder
- **THEN** it is not reported as a conflict

### Requirement: The user is asked once per import

The system SHALL present all conflicts of one import as a single decision point
offering overwrite-all, skip-all, or a per-file choice. It SHALL NOT interrupt
the user once per conflicting file.

#### Scenario: Ten conflicts in one import

- **WHEN** 10 of 50 selected files conflict
- **THEN** the user is asked once, with the 10 names listed
- **AND** the 40 non-conflicting files are not blocked by that decision

### Requirement: Overwrite preserves the document identity

When the user chooses to overwrite, the system SHALL replace the content of the
existing document and SHALL preserve its `document_uid`. It SHALL NOT create a
second document, and SHALL NOT leave the previous content indexed.

#### Scenario: A cited document is overwritten

- **WHEN** a document referenced by an existing agent answer is overwritten
- **THEN** that reference still resolves
- **AND** it resolves to the new content

#### Scenario: Re-indexing follows an overwrite

- **WHEN** a document is overwritten
- **THEN** its previous extracted content and vectors are replaced by the new ones
- **AND** a search no longer returns the previous content

#### Scenario: Quota reflects the difference only

- **WHEN** a 2 MB document is overwritten by a 3 MB file
- **THEN** the team's storage usage increases by 1 MB, not by 3 MB

### Requirement: Skip leaves the existing document untouched

When the user chooses to skip a conflicting file, the system SHALL import
neither its content nor its metadata, SHALL leave the existing document
unchanged, and SHALL report the file as skipped.

#### Scenario: A file is skipped

- **WHEN** the user skips a conflicting file
- **THEN** the existing document keeps its content, its identifier and its position in the folder
- **AND** the skipped file is reported to the user as skipped, not as failed

### Requirement: A conflict appearing after the check is not resolved silently

The pre-check is an optimisation, not a guarantee. The system SHALL re-check at
write time, and SHALL return a file that became conflicting in between as a
conflict still to be resolved.

#### Scenario: A teammate imports the same name concurrently

- **WHEN** a teammate imports the same name between the check and the write
- **THEN** the file is returned as a conflict to resolve
- **AND** it is neither silently overwritten nor reported as a failure

### Requirement: A conflicting file without a decision is refused

The system SHALL refuse to import a conflicting file carrying no decision,
rather than choosing one on the user's behalf.

#### Scenario: Decision missing

- **WHEN** an import request carries a conflicting file with no overwrite or skip decision
- **THEN** the request is refused with an error naming that file
- **AND** no document is created, modified or deleted
