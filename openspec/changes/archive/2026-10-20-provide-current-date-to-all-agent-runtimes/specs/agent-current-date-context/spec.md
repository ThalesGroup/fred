## Purpose

Provide a current calendar date to all supported agent execution models without changing stored prompts.

## ADDED Requirements

### Requirement: Runtime supplies today's date across execution models

The ReAct, Deep, and Graph runtimes SHALL include the current UTC calendar date in model input at execution time and instruct the model to answer a request for today's date without a time. This SHALL apply to existing and new agents regardless of stored agent prompts or admin platform prompt overrides. Stored prompt values SHALL remain unchanged.

#### Scenario: Existing ReAct or Deep agent has a saved prompt

- **WHEN** the agent invokes its model using a saved prompt and an admin platform prompt override
- **THEN** the model input includes the current UTC date in the platform instructions and keeps both saved prompt values

#### Scenario: Graph agent invokes a model

- **WHEN** a Graph node invokes a streaming or structured model through the supported runtime interface
- **THEN** the model messages include the current UTC date and date-only answer guidance without changing the caller's messages

#### Scenario: Invocation crosses a UTC date boundary

- **WHEN** an agent invokes the model after the UTC calendar date has changed
- **THEN** the newly composed model input contains the new date without requiring a restart or prompt update
