## MODIFIED Requirements

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
