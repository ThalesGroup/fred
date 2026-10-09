# Deliverable Generation Specification

## Purpose

Make long document, presentation, and HTML composition visible before publication, while preserving the existing deliverable tools and their output contracts.

## Requirements

### Requirement: Preparation precedes composition

The writable-document, PPT-filler, and HTML-artifact capabilities SHALL each expose a distinct preparation tool accepting only a short title. Their instructions MUST require the agent to call preparation and wait for its result before composing a new or revised deliverable's full publication arguments in a subsequent model round. Necessary research and clarification SHALL precede preparation. Preparation MUST NOT invoke another model or write, render, or publish a deliverable.

#### Scenario: Model does not emit reasoning

- **WHEN** an agent follows a deliverable capability's instructions using a model without visible reasoning text
- **THEN** a short preparation call and result appear before the model generates the full arguments for the publication call
- **AND** the preparation and publication calls belong to separate model rounds

#### Scenario: Preparation alone

- **WHEN** preparation succeeds but publication has not been called
- **THEN** no document row, workspace file, presentation, preview, or empty deliverable placeholder is created

### Requirement: Preparation follows capability availability

Each preparation tool SHALL be exposed only through its selected capability and current execution-model support. PPT preparation SHALL be absent whenever the configured-template gate also withholds the PPT publication tool. Enabling all three capabilities together MUST produce three unambiguous preparation tools.

#### Scenario: Missing PPT configuration

- **WHEN** an agent has no usable configured PPT template and the publication tool is unavailable
- **THEN** its PPT preparation tool is also unavailable

#### Scenario: Multiple enabled deliverable capabilities

- **WHEN** the three deliverable capabilities are enabled on a supported agent
- **THEN** all three preparation tools are distinct and each directs the agent to its corresponding publication tool

### Requirement: Composition activity has an honest lifecycle

During a live turn, the chat SHALL show a localized deliverable-specific composition indication after successful preparation and before the corresponding publication call. The indication MUST remain visible without model reasoning text. It SHALL yield to publication activity, errors, human-input pauses, cancellation, or turn completion. The preparation tool's row MUST report completion when its result arrives, rather than pretending that the tool remains running. Composition activity MUST be scoped to the current turn and execution and MUST NOT reactivate in completed history.

#### Scenario: Waiting for publication arguments

- **WHEN** document, presentation, or HTML preparation has succeeded and the live model is composing publication arguments
- **THEN** the chat continues displaying the corresponding composition label in French or English
- **AND** the preparation tool row remains completed

#### Scenario: Publication starts

- **WHEN** the corresponding publication call appears
- **THEN** composition activity ends and the chat identifies the writing or rendering step

#### Scenario: Interrupted composition

- **WHEN** an error, cancellation, human-input pause, or turn completion occurs after preparation without a publication call
- **THEN** no composition indication remains active and no successful deliverable is implied

#### Scenario: History and execution isolation

- **WHEN** a completed exchange is reloaded, a new turn starts, or another execution produces a deliverable
- **THEN** an earlier preparation does not create composition activity in that completed exchange, new turn, or other execution

### Requirement: Publication remains compatible

The existing publication tools SHALL retain their accepted arguments, direct-call behavior, output parts, validation, and download/edit/preview contracts. Preparation MUST NOT become a mandatory server-side prerequisite for existing callers. Revisions SHALL continue reusing existing document or artifact identifiers. Publication of already-composed workspace Markdown SHALL retain its direct path.

#### Scenario: Direct publication

- **WHEN** an existing caller invokes `write_document`, `fill_ppt_template`, or `render_html_artifact` without preparation
- **THEN** the call retains its previous behavior and output contract

#### Scenario: Revise an existing deliverable

- **WHEN** an agent prepares a revision and publishes it with the existing document or artifact identifier
- **THEN** the existing editor or preview updates according to its current contract without creating an extra placeholder or duplicate deliverable

#### Scenario: Open completed workspace Markdown

- **WHEN** an agent opens an already-composed workspace Markdown file with the existing file-based document tool
- **THEN** the file is published without requiring a composition-preparation call
