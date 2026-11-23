## Purpose

Defines how native Deep sub-agents contribute evidence and working data to a parent turn while the parent retains ownership of user-facing deliverables and chat output.

## ADDED Requirements

### Requirement: User-facing deliverables belong to the parent

Capabilities that publish a downloadable file or other user-facing deliverable SHALL be available to the Deep parent and SHALL NOT be available to native sub-agents. A sub-agent SHALL be able to return working data to its parent without publishing a deliverable. The parent SHALL decide whether to create a final deliverable. The child's tool instructions SHALL list only tools it can use.

#### Scenario: Delegated spreadsheet preparation

- **GIVEN** a Deep parent with a spreadsheet-creation capability and a native sub-agent
- **WHEN** the parent delegates data preparation
- **THEN** the sub-agent can return its prepared data but cannot invoke the spreadsheet-creation tool
- **AND** the parent can create a downloadable workbook from that data

#### Scenario: Direct child attempt to invoke a parent-only tool

- **WHEN** a native sub-agent attempts to call a tool from a parent-only capability by name
- **THEN** the tool does not run or create a file
- **AND** the parent turn remains able to report the failed child task

### Requirement: Child evidence reaches the parent turn without exposing child execution

Sources and non-deliverable UI parts from allowed child tools SHALL reach the parent exchange and persisted history. A completed invocation SHALL carry its evidence in its final event; a paused invocation SHALL carry it in its awaiting-human event. Child text, reasoning and tool events SHALL remain private; the parent SHALL answer.

#### Scenario: Child retrieves cited documents

- **WHEN** a sub-agent returns document sources and the parent invocation completes without pausing
- **THEN** the parent turn carries those sources in its final event and saved history
- **AND** the chat does not display the child's private messages or tool-call trace entries as separately authored content

#### Scenario: Child produces a non-deliverable UI part

- **WHEN** an allowed child tool returns a non-deliverable UI part and the parent invocation completes without pausing
- **THEN** the parent's final event and saved history contain that part once
- **AND** no child-authored file card is displayed

### Requirement: Delegated evidence is collected on every Deep turn

The parent SHALL collect eligible child evidence whether platform skills are enabled or disabled. Aggregation SHALL preserve the existing parent result, avoid duplicate sources and parts, and SHALL NOT repeat child evidence when a paused exchange resumes.

#### Scenario: Skills disabled

- **GIVEN** a Deep agent with platform skills disabled
- **WHEN** an allowed child tool returns sources or a non-deliverable UI part and the parent invocation completes without pausing
- **THEN** the parent final event contains that evidence

#### Scenario: Several children or a resumed exchange

- **WHEN** several children return overlapping evidence before a pause and the parent resumes after human approval
- **THEN** the awaiting-human event and its saved pause metadata carry each distinct source and part once
- **AND** the completed exchange displays that evidence with the parent's final answer once after resume
- **AND** no child result is replayed as a new user-visible tool call
