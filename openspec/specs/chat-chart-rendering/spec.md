# chat-chart-rendering Specification

## Purpose

Enables Fred agents to turn bounded tabular results into typed, persistent chat charts that users can inspect without parsing or re-running the source query.

## Requirements

### Requirement: Shared chart tool availability

The runtime SHALL expose `chart.render` once to ReAct, Deep, and Graph agents without requiring an agent-specific declaration or an application tool invoker. An explicit declaration of the same tool SHALL not add a second callable instance.

#### Scenario: ReAct or Deep chart call
- **WHEN** an agent uses `chart.render` with valid tabular rows
- **THEN** the call returns a short textual result and a typed chart part in the final response

#### Scenario: Graph chart call
- **WHEN** a Graph node calls `chart.render` without an agent-level declaration
- **THEN** the runtime permits the call and carries its typed chart part through the tool result and final response

#### Scenario: Explicit declaration
- **WHEN** an agent explicitly declares `chart.render`
- **THEN** the runtime offers exactly one callable chart tool

#### Scenario: Python-authored tool call
- **WHEN** a Python-authored tool calls `chart.render` through `ToolContext.invoke_tool`
- **THEN** the same local handler returns a typed chart part or a validation error without a part

### Requirement: Bounded and faithful chart data

`chart.render` SHALL accept a chart type, title, row objects, and column mapping without executing SQL or fetching data. It SHALL reject invalid mappings, non-finite numeric series, unsupported chart types, or inputs exceeding the published row and serialized-size limits rather than silently truncating or changing values. The returned chart part SHALL contain the validated rows needed to render the result.

#### Scenario: SQL result is charted
- **WHEN** a tabular query returns rows that the agent passes to `chart.render` with valid axis and series keys
- **THEN** the chart part contains those rows and mappings without another data request

#### Scenario: Invalid numeric column
- **WHEN** a plotted series contains a non-numeric value other than null
- **THEN** the tool reports a validation error and emits no chart part

#### Scenario: Invalid ReAct or Deep tool arguments
- **WHEN** a ReAct or Deep agent calls the chart tool with missing or invalid arguments
- **THEN** the tool returns a validation error without a chart part and the agent turn can continue

#### Scenario: Oversized result
- **WHEN** rows exceed 50 entries or the chart payload exceeds 50,000 serialized characters
- **THEN** the tool reports the applicable limit and emits no partial chart

#### Scenario: Table view
- **WHEN** a valid request chooses the table view with scalar row values
- **THEN** the rows remain available without requiring a numeric series

### Requirement: Typed charts render in chat

The chat SHALL render a typed chart part as the requested bar, line, area, pie, or table view and expose its underlying rows in a readable table. Chart text SHALL be treated as text, and unsupported or malformed parts SHALL leave a readable fallback. Chat SHALL NOT turn arbitrary assistant prose, Markdown tables, or JSON code blocks into a chart.

#### Scenario: Live and restored chart
- **WHEN** an agent returns a valid chart part and the user later reloads the conversation
- **THEN** the same chart data and view are visible both live and after reload

#### Scenario: Chart after human input pause
- **WHEN** a Graph node emits a chart part before requesting human input
- **THEN** the awaiting-human event retains the chart part for the visible exchange

#### Scenario: Plain text remains plain text
- **WHEN** an assistant writes tabular Markdown or chart-shaped JSON without a typed chart part
- **THEN** the chat displays that content as text or code

### Requirement: SQL chart guidance

The SQL expert's tool instructions SHALL direct the agent to render a chart when the user requests one or when a chart materially clarifies a trend, comparison, or distribution in the answer. The instructions SHALL direct the agent to answer without a chart when text or a compact table conveys the result just as clearly. For any chart, the agent SHALL use actual returned query rows, choose a suitable chart type, and avoid presenting values that were not returned by the query. The agent SHALL disclose query truncation in its answer.

#### Scenario: Visualization of an aggregate query
- **WHEN** a SQL aggregate returns bounded rows whose trend, comparison, or distribution is materially clearer in a chart
- **THEN** the agent is instructed to render a suitable chart from those rows and explain the result and any query truncation

#### Scenario: User requests a chart
- **WHEN** the user asks for a chart in the question or in a later turn
- **THEN** the agent is instructed to render a suitable chart from actual query rows and explain any query truncation

#### Scenario: Chart adds no value
- **WHEN** text or a compact table conveys the result just as clearly and the user did not ask for a chart
- **THEN** the agent is instructed to answer without rendering a chart

### Requirement: Chart downloads

Chat SHALL offer a download menu with an Excel workbook of the rows stored in a valid chart part and a PNG download of a plotted bar, line, area, or pie chart. Exports SHALL use the displayed chart part without running the source query again. The Excel workbook SHALL retain the stored columns and values without executing text as formulas, and the PNG SHALL contain the rendered graphic on a transparent background. The table view SHALL offer Excel without a PNG action. Export errors SHALL be visible to the user.

#### Scenario: Download chart data
- **WHEN** a user selects Excel from the download menu of a valid chart or table part
- **THEN** an `.xlsx` file contains the part's bounded rows and columns with their scalar types

#### Scenario: Download graphic
- **WHEN** a user selects PNG from the download menu of a valid plotted chart part
- **THEN** the file contains the visible chart as a PNG image with a transparent background

#### Scenario: Restored chart
- **WHEN** a user reopens a conversation with a saved chart part
- **THEN** the same Excel and applicable PNG downloads remain available

#### Scenario: Export failure
- **WHEN** the browser cannot produce the requested file
- **THEN** the user sees a localized error and the chat remains usable
