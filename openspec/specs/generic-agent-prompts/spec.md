## Purpose

Define the shipped default instructions of Fred's generic ReAct and Deep assistants so they can answer basic date questions using runtime context.

## Requirements

### Requirement: Generic assistants receive the current date in their default prompts

The default English and French system prompts for the generic ReAct and Deep assistants SHALL include the date at execution time and instruct the assistant to give that date without a time when asked for today's date. A stored non-blank system prompt SHALL retain precedence over the default.

#### Scenario: Default generic assistant is asked for today's date

- **WHEN** a new generic ReAct or Deep assistant uses its shipped default prompt in either supported language
- **THEN** the prompt contains the execution date and instructs the assistant to answer a date request without a time

#### Scenario: Instance has a stored system prompt

- **WHEN** a generic ReAct or Deep instance has a non-blank stored system prompt, including a previous default copied on enrollment
- **THEN** the override remains the effective agent prompt and the new default does not replace it
