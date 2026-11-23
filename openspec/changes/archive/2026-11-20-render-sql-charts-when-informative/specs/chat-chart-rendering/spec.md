## MODIFIED Requirements

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
