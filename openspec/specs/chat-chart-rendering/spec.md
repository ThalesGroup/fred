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

The SQL expert's tool instructions SHALL answer a tabular question without automatically rendering a chart. When a chart would clarify the result and the user has not requested one, the instructions SHALL direct the agent to offer a chart in its answer and wait for the user's choice. When the user explicitly requests a chart, including by accepting an earlier offer, the instructions SHALL direct the agent to use actual returned query rows, choose a suitable chart type, and avoid presenting values that were not returned by the query. The agent SHALL disclose query truncation in its answer.

#### Scenario: Visualization of an aggregate query
- **WHEN** a SQL aggregate returns bounded rows suited to a chart and the user did not ask for a chart
- **THEN** the agent is instructed to answer the question, offer a chart, and not call the chart tool yet

#### Scenario: User requests a chart
- **WHEN** the user asks for a chart in the question or accepts the agent's offer later
- **THEN** the agent is instructed to render a suitable chart from actual query rows and explain any query truncation

#### Scenario: Chart adds no value
- **WHEN** a chart would not clarify the tabular answer and the user did not ask for one
- **THEN** the agent is instructed to answer without offering or rendering a chart
