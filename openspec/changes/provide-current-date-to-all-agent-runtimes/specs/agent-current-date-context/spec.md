## Purpose

Give every supported agent model invocation a reliable current calendar date without changing stored prompts or requiring a clock tool.

## ADDED Requirements

### Requirement: Supported agent calls receive the current UTC date

The runtime SHALL supply the current UTC calendar date to the model at each ReAct, Deep root, Deep child, and supported Graph model invocation, whether or not the agent prompt mentions a date. The supplied context SHALL contain a date, not a current time. Existing agent instances SHALL receive this behavior when their runtime pods are updated, without editing their stored prompts.

#### Scenario: Existing agents on updated pods

- **GIVEN** an existing ReAct or Deep agent whose stored prompt does not use `{today}`
- **WHEN** its updated runtime makes a model call
- **THEN** the model input contains the current UTC calendar date without a current hour
- **AND** the stored prompt and admin platform prompt override remain unchanged and effective

#### Scenario: Deep child call

- **WHEN** a Deep child invokes its model on an updated runtime
- **THEN** its model input contains the current UTC calendar date

#### Scenario: Supported Graph calls

- **WHEN** a Graph node makes a streaming or structured model call through the supported `NodeContext` methods
- **THEN** the effective model input contains the current UTC calendar date
- **AND** the messages supplied by the caller remain unchanged

### Requirement: Date context stays current within a conversation

The runtime SHALL calculate the date for each model invocation. A `{today}` token in a ReAct or Deep agent template or attached context prompt SHALL resolve to the same date supplied for that invocation. The token SHALL NOT be required for an agent to receive the date. An authored `{today}` in an admin platform prompt or Graph prompt SHALL retain its existing literal behavior. The runtime-supplied date SHALL be presented as the reference for the real current date when an older saved prompt conflicts with it.

#### Scenario: Conversation crosses UTC midnight

- **GIVEN** a conversation whose next model call occurs after UTC midnight
- **WHEN** that call is made, including within an ongoing turn or after a retry
- **THEN** the model receives the new UTC date
- **AND** any `{today}` token in the effective prompt resolves to that same date

#### Scenario: Explicit date placement in a template

- **GIVEN** a ReAct or Deep agent template or attached context prompt containing `{today}`
- **WHEN** the updated runtime makes a model call
- **THEN** the token is replaced with the same date supplied by the runtime for that call
- **AND** the stored template is not rewritten

#### Scenario: Prompts without token rendering

- **GIVEN** an admin platform prompt override or Graph prompt containing literal `{today}`
- **WHEN** the updated runtime makes a supported model call
- **THEN** that authored text remains literal
- **AND** the model receives the current date separately from the runtime

#### Scenario: Stale date in a saved prompt

- **GIVEN** a saved agent prompt that identifies an earlier date as today
- **WHEN** the updated runtime makes a model call
- **THEN** the model input presents the current runtime date as the authoritative date for the real present day
- **AND** the saved prompt is not rewritten

### Requirement: Date answers are guided without a clock value

The model input SHALL instruct the agent to answer an ordinary request for today's date with the date alone, without a current time or UTC label. For an explicitly requested local date, it SHALL instruct the agent to state that only the UTC date is known rather than claim a local date it cannot determine.

#### Scenario: Ordinary date request

- **WHEN** a user asks what today's date is
- **THEN** the model input includes guidance to answer with the date alone, without a current time or UTC label

#### Scenario: Explicit local-date request

- **WHEN** a user asks for today's date in France
- **THEN** the model input includes guidance to state the limitation of the available UTC date rather than claim a French local date
