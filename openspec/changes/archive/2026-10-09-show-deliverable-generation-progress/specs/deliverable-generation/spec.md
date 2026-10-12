## MODIFIED Requirements

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
