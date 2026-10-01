## MODIFIED Requirements

### Requirement: Every phase of an import is distinguished

For each file the system SHALL show which phase it is in, across the browser's
transfer and each phase the ingestion workflow reports for itself — document
preparation, content extraction, indexing — and SHALL indicate when the file
becomes usable. A single merged indicator is not sufficient.

A file the ingestion workflow has not started yet SHALL be shown as waiting,
distinct from a phase under way: no running indicator until the workflow
reports the file as running.

The system SHALL NOT display a completion fraction for an import. No phase
reports a fraction of itself, so any percentage would be fabricated.

#### Scenario: A file finishes uploading but is still being analysed

- **WHEN** a file has been transferred but its analysis is not finished
- **THEN** it is shown as being analysed, not as ready
- **AND** the user can tell it is not yet usable

#### Scenario: A transferred file waits for the ingestion workflow

- **WHEN** a file has been transferred and the ingestion workflow has not started it
- **THEN** the phase it is about to start is shown as waiting, without a running indicator
- **AND** its status reads as waiting rather than naming that phase
- **WHEN** the workflow reports the file as running
- **THEN** the phase is shown as under way

#### Scenario: The server names the phase it has reached

- **WHEN** the ingestion workflow reports a phase for a file
- **THEN** that phase is shown as the one under way, named
- **AND** the phases before it are shown as complete

#### Scenario: A deployment reports no phase between two it does report

- **WHEN** a file completes without the server having named every phase
- **THEN** no phase is left shown as unreached

#### Scenario: A file becomes usable

- **WHEN** a file's analysis completes
- **THEN** it is shown as ready
- **AND** its entry leaves the panel shortly afterwards, so the panel holds
  only what still needs following
