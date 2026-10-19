## MODIFIED Requirements

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
