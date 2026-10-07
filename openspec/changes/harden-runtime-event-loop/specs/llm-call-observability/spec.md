## ADDED Requirements

### Requirement: Shared runtime work preserves concurrent streaming progress

Cloud conversation-file listings and supported synchronous authored tools SHALL perform their blocking work outside the event loop used by concurrent model calls. Results, caller context and asynchronous tool execution SHALL remain compatible. Cancellation SHALL NOT automatically replay an already-started synchronous tool. Runtime diagnostics MUST NOT equate absence of observed chunks with proof of upstream silence.

#### Scenario: Cloud listing during another model call
- **WHEN** a conversation lists many files and inferred directories while another model call is active
- **THEN** network and listing conversion work do not monopolize its event-loop thread, and the sorted listing preserves existing entries and metadata

#### Scenario: Synchronous authored tool
- **WHEN** a supported synchronous tool waits for blocking work
- **THEN** unrelated asynchronous work can progress and the tool observes the caller context, with its result or exception delivered once

#### Scenario: Asynchronous authored tool
- **WHEN** an asynchronous tool or callable needs the owner event loop
- **THEN** it continues executing on that loop with unchanged return and error behavior
