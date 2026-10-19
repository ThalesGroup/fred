# document-import-experience Specification

## Purpose
Give the user back the application as soon as an import starts, and show them
what is happening to each file until it is usable, wherever they are in the
product.

## Requirements

### Requirement: The dialog does not hold the user

The import dialog SHALL close as soon as the selected files are accepted for
import, and SHALL NOT remain open while files are transferred or prepared.

#### Scenario: A large import starts

- **WHEN** the user confirms an import of 50 files
- **THEN** the dialog closes without a perceptible wait
- **AND** the rest of the application is immediately usable

### Requirement: A running import survives leaving its page

An import SHALL continue, and SHALL keep being followed, while the user is
anywhere else in the application. Its surface is the Resources page of the team
it belongs to: the system SHALL show the number of files in progress there
without the panel being opened, and SHALL restore the full list on return.

Deliberately not shown elsewhere: an import is something the user starts on one
page and comes back to, not a background job needing an application-wide
indicator.

#### Scenario: The user leaves the Resources page

- **WHEN** an import is running and the user navigates elsewhere
- **THEN** the transfer continues and its progress keeps being recorded
- **AND** returning to the Resources page shows each file at the phase it has
  reached, with the count visible before the panel is opened

#### Scenario: The user reloads the page

- **WHEN** the user reloads while an import is still running
- **THEN** every file the server already has is still shown, with its current
  phase
- **AND** any file that never reached the server is listed as a failed import,
  named, with the cause it was given — or the interruption itself when there
  was none — and an action to send it again

### Requirement: Every phase of an import is distinguished

For each file the system SHALL distinguish transfer, durable original storage and
any processing phases actually executed. Knowledge-flow ingestion SHALL show the
phases its workflow reports, including preparation, extraction and indexing.
Manager original-storage imports SHALL terminate as stored and downloadable, and
SHALL NOT display fabricated ingestion phases or claim search/agent readiness.

The system SHALL NOT display a completion fraction for an import. No phase reports
a fraction of itself, so any percentage would be fabricated.

#### Scenario: A file finishes uploading but is still being analysed
- **WHEN** a file has been transferred to knowledge-flow but its analysis is not finished
- **THEN** it is shown as being analysed, not as ready
- **AND** the user can tell it is not yet usable for retrieval

#### Scenario: The server names the phase it has reached
- **WHEN** the ingestion workflow reports a phase for a file
- **THEN** that phase is shown as the one under way, named
- **AND** the phases before it are shown as complete

#### Scenario: A deployment reports no phase between two it does report
- **WHEN** a file completes without the server having named every executed phase
- **THEN** no executed phase is left shown as unreached

#### Scenario: A file becomes usable
- **WHEN** a file's analysis completes
- **THEN** it is shown as ready
- **AND** its entry leaves the panel shortly afterwards, so the panel holds only what still needs following

#### Scenario: An original is stored without processing
- **WHEN** manager confirms durable original storage
- **THEN** the panel reports the file as stored and downloadable, and its completed entry leaves the panel shortly afterwards
- **AND** the document row does not claim that extraction, indexing or agent availability has occurred

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

The cause SHALL survive a reload for a file the server never received, and the
action offered SHALL then be to send the file again rather than to retry — the
browser no longer holds it. No action SHALL be offered for a cause that sending
the file again cannot change.

#### Scenario: One file among fifty fails

- **WHEN** one file fails and the user is looking at another page
- **THEN** the failure is still listed when they return
- **AND** the other 49 files continue

#### Scenario: A failure is retried

- **WHEN** the user retries a failed file
- **THEN** the file is imported again without re-selecting it from disk, if its content is still available to the browser
- **AND** the outcome replaces the previous failure in the panel

### Requirement: An interrupted import keeps what arrived

If an import is interrupted, published originals SHALL remain available. Files
accepted for knowledge-flow processing SHALL continue to be analysed. The system
SHALL name known files that were not successfully stored and offer a safe way to
finish their import. For manager, an uncertain response SHALL first be resolved
using the actor's durable receipt; interruption SHALL NOT initiate a fresh upload
of an already committed document.

#### Scenario: The tab is closed mid-import
- **WHEN** the user closes the tab during an import of 50 files and returns later
- **THEN** published files are unaffected
- **AND** the panel names known files that were not successfully stored
- **AND** the user is offered a way to finish the import for those files only

#### Scenario: The browser has cleared its stored data
- **WHEN** the user returns in a browser that wipes site data between sessions
- **THEN** published files and still-retained actor-owned receipts are recoverable from the server under current rights
- **AND** nothing is claimed about files the server never received, and no action is offered for them

#### Scenario: The original browser file is unavailable
- **WHEN** a retry needs bytes after reload and the browser no longer holds the File
- **THEN** the existing retry presentation requests file re-selection and verifies its target/content binding
- **AND** a known stored result is not uploaded again

### Requirement: The upload stage can be cancelled

The system SHALL let the user stop files that have not yet been transferred.
Cancelling SHALL NOT affect files already received or imply document deletion.
Knowledge-flow documents retain their existing removal workflow; manager
original-storage imports SHALL leave published originals intact and make no claim
that document deletion is available in this slice.

#### Scenario: Wrong destination folder
- **WHEN** the user realises mid-import that the destination is wrong and cancels
- **THEN** queued files not yet being transferred are not imported
- **AND** files already received are unaffected
- **AND** no manager document is silently deleted or moved

### Requirement: The wording names the action

The import control SHALL name importing rather than saving, and SHALL state how
many files it will import. The dialog title SHALL be plural.

#### Scenario: Twelve files selected

- **WHEN** 12 files are selected
- **THEN** the control reads "Importer 12 fichiers" in French and "Import 12 files" in English
