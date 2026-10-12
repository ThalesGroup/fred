# Deliverable Generation Specification

## Purpose

Expose the start of document, presentation, and HTML creation through ordinary preparation tool calls while preserving publication contracts.

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

Preparation and publication SHALL appear as ordinary tool calls with their actual call/result status. Preparation MUST complete when its short acknowledgement returns; the chat MUST NOT imply that this tool is still running while the model composes the publication arguments in a later round. Publication SHALL use the existing tool behavior. No special composition timer, pulse, or persisted activity is required.

#### Scenario: Preparation completes before composition

- **WHEN** a document, presentation, or HTML preparation call returns successfully
- **THEN** its tool row reports completion
- **AND** the model can compose the full publication arguments in the next round without the preparation row pretending to run

#### Scenario: Publication starts

- **WHEN** the corresponding publication call appears
- **THEN** it has its ordinary in-progress status until its result arrives

#### Scenario: Interrupted composition

- **WHEN** an error, cancellation, or human-input pause occurs after preparation without publication
- **THEN** the completed preparation does not imply a successfully published deliverable

#### Scenario: History and execution isolation

- **WHEN** a completed exchange is reloaded, a new turn starts, or another execution produces a deliverable
- **THEN** the earlier preparation retains only its own recorded call/result state

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
