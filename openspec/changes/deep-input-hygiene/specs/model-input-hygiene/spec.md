# Spec Delta

## Purpose

Keep provider-bound conversation history valid while preserving the original checkpoint messages for persistence and replay.

## ADDED Requirements

### Requirement: Request-only message sanitation

ReAct and Deep parent model requests SHALL sanitize incomplete tool exchanges and provider reasoning through shared hygiene without mutating persisted input messages. Deep SHALL disable message-count trimming while retaining the existing character budget.

#### Scenario: Deep replays interrupted tool history
- **WHEN** a Deep parent request includes dangling tool calls, paired tool results and open-turn reasoning
- **THEN** the model receives valid tool pairing and reasoning as supported text
- **AND** the original checkpoint messages remain unchanged

#### Scenario: Deep history exceeds the ReAct message count
- **WHEN** a Deep parent history exceeds the ReAct message-count limit but fits the character budget
- **THEN** hygiene does not discard messages based on their count

#### Scenario: Oversized open turn
- **WHEN** the current Deep turn cannot fit the character budget
- **THEN** the existing readable oversized-turn error is raised before provider invocation

### Requirement: Provider-compatible message names

Shared model-input hygiene SHALL remove per-message names from copied inputs while preserving content, tool-call IDs and tool results. The OpenAI-compatible provider payload SHALL omit unsupported assistant names.

#### Scenario: Named assistant replay
- **WHEN** a model request replays a named assistant message with a paired tool result
- **THEN** its serialized provider message omits the name field and preserves the tool-call identity
- **AND** the original assistant name remains present in checkpoint history

#### Scenario: Ordinary unnamed history
- **WHEN** shared hygiene receives unnamed messages
- **THEN** name sanitation leaves those message objects unchanged
