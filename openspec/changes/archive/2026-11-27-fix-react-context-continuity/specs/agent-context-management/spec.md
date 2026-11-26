# Spec Delta

## Purpose

Keeps the instructions and continuation state of ReAct conversations available to the model while bounding the context sent on each call.

## ADDED Requirements

### Requirement: Completed turns retain conversational continuity under a budget

When ReAct model input exceeds its configured history budget, the runtime SHALL retain the user message and final assistant answer of the latest completed turn before discarding older completed tool results. It SHALL preserve additional completed conversation turns that fit and remove older turns in order when necessary.

#### Scenario: Continue after large tool results

- **GIVEN** a completed turn whose tool results exceed the history budget and whose final answer states a next step
- **WHEN** the user sends a short approval or asks the agent to continue
- **THEN** the model input contains the previous user request, the final answer, and the new user message
- **AND** completed tool results may be absent from that model input

#### Scenario: History already fits

- **GIVEN** a conversation whose model input fits the history budget
- **WHEN** ReAct prepares a model call
- **THEN** its conversation messages remain unchanged by context compaction

### Requirement: Active work and tool identities remain valid

The runtime SHALL preserve leading system context, the current user message, and its in-progress tool-call/result groups in the model input. If these and the latest completed conversational turn cannot fit the configured history budget, the runtime SHALL return an explicit size error rather than send an incomplete request to the model.

#### Scenario: Current turn contains tool calls

- **GIVEN** an active turn with a user message, a tool call, and its result
- **WHEN** earlier completed turns are compacted
- **THEN** the active user message and matching tool-call/result pair remain in order

#### Scenario: Child agent retains leader context

- **GIVEN** a child ReAct conversation with leading system context from its team leader
- **WHEN** previous completed turns are compacted
- **THEN** the leader context remains in the model input

#### Scenario: Active context cannot fit

- **GIVEN** an active turn that exceeds the available history budget on its own
- **WHEN** ReAct prepares another model call
- **THEN** the turn fails with an explicit size error
- **AND** no model request is sent without the active user message

### Requirement: Compaction does not rewrite durable history

ReAct SHALL apply context compaction only to the model request. Stored checkpoint messages and user-visible conversation history SHALL remain available in their original form.

#### Scenario: Reload after compaction

- **GIVEN** a model call that required context compaction
- **WHEN** the conversation is reloaded
- **THEN** its original user, assistant, and tool events remain in durable history
