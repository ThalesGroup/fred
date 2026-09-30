## Purpose

Give the user back the application as soon as an import starts, and show them
what is happening to each file until it is usable, wherever they are in the
product.

## ADDED Requirements

### Requirement: The dialog does not hold the user

The import dialog SHALL close as soon as the selected files are accepted for
import, and SHALL NOT remain open while files are transferred or prepared.

#### Scenario: A large import starts

- **WHEN** the user confirms an import of 50 files
- **THEN** the dialog closes without a perceptible wait
- **AND** the rest of the application is immediately usable

### Requirement: A running import is visible from anywhere

The system SHALL show running imports in a surface reachable from any page,
showing at least the number of files in progress without being opened.

#### Scenario: The user leaves the Resources page

- **WHEN** an import is running and the user navigates elsewhere
- **THEN** the import remains visible and its progress keeps updating

#### Scenario: The user reloads the page

- **WHEN** the user reloads while an import is still running
- **THEN** the import is still shown, with its current progress

### Requirement: Upload and analysis are distinguished

For each file the system SHALL show which of two stages it is in — being
uploaded, or being analysed — and SHALL indicate when it becomes usable. A
single merged progress indicator is not sufficient.

#### Scenario: A file finishes uploading but is still being analysed

- **WHEN** a file has been transferred but its analysis is not finished
- **THEN** it is shown as being analysed, not as ready
- **AND** the user can tell it is not yet usable

#### Scenario: A file becomes usable

- **WHEN** a file's analysis completes
- **THEN** it is shown as ready

### Requirement: The panel shows the user's own imports

The panel SHALL list the imports started by the current user and SHALL NOT list
other users' imports.

#### Scenario: A teammate imports at the same time

- **WHEN** a teammate is importing into the same folder
- **THEN** the user's panel does not list the teammate's files

### Requirement: A failed file persists with a readable cause

A file that fails SHALL remain listed with a cause written for a non-technical
reader and a retry action, until the user retries or dismisses it. It SHALL NOT
be reported only by a transient notification, and SHALL NOT stop the other
files.

#### Scenario: One file among fifty fails

- **WHEN** one file fails and the user is looking at another page
- **THEN** the failure is still listed when they return
- **AND** the other 49 files continue

#### Scenario: A failure is retried

- **WHEN** the user retries a failed file
- **THEN** the file is imported again without re-selecting it from disk, if its content is still available to the browser
- **AND** the outcome replaces the previous failure in the panel

### Requirement: An interrupted import keeps what arrived

If an import is interrupted, files already received SHALL continue to be
analysed, and the system SHALL name the files that were not received and offer
to finish the import.

#### Scenario: The tab is closed mid-import

- **WHEN** the user closes the tab during an import of 50 files and returns later
- **THEN** the files already received are unaffected
- **AND** the panel names the files that were not received
- **AND** the user is offered a way to finish the import for those files only

### Requirement: The upload stage can be cancelled

The system SHALL let the user stop files that have not yet been transferred.
Cancelling SHALL NOT affect files already received.

#### Scenario: Wrong destination folder

- **WHEN** the user realises mid-import that the destination is wrong and cancels
- **THEN** files not yet transferred are not imported
- **AND** files already received are unaffected and can be removed like any document

### Requirement: The wording names the action

The import control SHALL name importing rather than saving, and SHALL state how
many files it will import. The dialog title SHALL be plural.

#### Scenario: Twelve files selected

- **WHEN** 12 files are selected
- **THEN** the control reads "Importer 12 fichiers" in French and "Import 12 files" in English
