## Purpose

Defines how one human-in-the-loop pause is identified, answered exactly once, and paired
with its answer in durable history, when several pauses can occur within a single turn.

## ADDED Requirements

### Requirement: One pause is identified by its occurrence, not by its interrupt alone

A human input request MAY carry an `occurrence_id` identifying one pause among those
sharing a LangGraph `interrupt_id`. A pause raised from inside a tool SHALL set
`occurrence_id` to that tool call's `tool_call_id`. A pause raised outside any tool call
MAY omit it.

#### Scenario: Pauses sharing an interrupt id are distinguishable

- **GIVEN** a turn raises three human input pauses that LangGraph reports under one
  `interrupt_id`
- **WHEN** each pause is emitted to the client
- **THEN** each carries a distinct `occurrence_id` taken from its own tool call

#### Scenario: A single platform pause keeps today's shape

- **GIVEN** a pause raised by the tool approval gate, outside any tool call
- **WHEN** it is emitted to the client
- **THEN** it carries no `occurrence_id` and is identified by its `interrupt_id` alone

#### Scenario: The identifier survives a resumed replay

- **GIVEN** a pause raised from a tool call, answered by the user
- **WHEN** LangGraph replays the resumed task from the top and reaches the same call
- **THEN** the `occurrence_id` is unchanged, because it derives from the tool call id
  rather than being generated per execution

### Requirement: A resume must name the exact occurrence it answers

A resume request SHALL carry `occurrence_id` whenever the occurrence it answers declares
one, and the runtime SHALL reject a resume whose `(interrupt_id, occurrence_id)` pair does
not match a currently pending occurrence. `occurrence_id` SHALL be valid only together
with `resume_payload`.

#### Scenario: An answer cannot be applied to a sibling pause

- **GIVEN** two pending pauses share an `interrupt_id` and differ by `occurrence_id`
- **WHEN** a resume arrives carrying the first pause's `occurrence_id`
- **THEN** only the first pause is resumed and the second stays pending

#### Scenario: A stale answer is refused

- **GIVEN** a pause that has already been answered and is no longer pending
- **WHEN** a late resume arrives carrying its `occurrence_id`
- **THEN** the runtime refuses it with a conflict rather than resuming a sibling or a
  later pause

#### Scenario: A missing occurrence id is refused when one is required

- **GIVEN** a pending occurrence that declares an `occurrence_id`
- **WHEN** a resume arrives carrying only the matching `interrupt_id`
- **THEN** the runtime refuses it with a conflict

#### Scenario: An occurrence id without a resume payload is invalid

- **GIVEN** an execute request carrying `occurrence_id` but no `resume_payload`
- **WHEN** the request is validated
- **THEN** it is rejected, exactly as `interrupt_id` already is in that case

### Requirement: Each occurrence is answerable exactly once

The durable single-use claim SHALL be scoped to one occurrence, so that answering one
pause never marks a sibling pause as claimed, started, or consumed.

#### Scenario: Two siblings are independently answerable

- **GIVEN** two pending pauses sharing an `interrupt_id`
- **WHEN** the first is answered and its claim reaches a terminal state
- **THEN** the second can still be claimed and answered

#### Scenario: One occurrence cannot be answered twice

- **GIVEN** two concurrent resume attempts naming the same `(interrupt_id, occurrence_id)`
  pair
- **WHEN** both reach the runtime
- **THEN** exactly one acquires the claim and the other is refused

### Requirement: A human answer records its text separately from its choice

`HitlResponsePart` SHALL record free-form text in a dedicated field and SHALL NOT store
typed text in `choice_id`. A response SHALL record the `occurrence_id` of the request it
answers when that request declared one.

#### Scenario: Free text is stored as text

- **GIVEN** a pause answered with free-form text and no choice
- **WHEN** the turn is persisted
- **THEN** the stored response carries the text in its text field and no `choice_id`

#### Scenario: A choice and a comment are both preserved

- **GIVEN** a pause answered by selecting an option and typing a comment
- **WHEN** the turn is persisted
- **THEN** the stored response carries both the selected `choice_id` and the comment text

#### Scenario: Existing stored responses stay readable

- **GIVEN** a response persisted before this change, whose `choice_id` holds typed text
- **WHEN** history is read back
- **THEN** it still loads and renders, without retroactive reinterpretation of that field

### Requirement: History pairs many requests and answers within one exchange

History reconstruction SHALL pair each human input request with its answer by
`occurrence_id` and SHALL NOT assume at most one request and one answer per exchange. A
request with no matching answer SHALL be reported as still pending.

#### Scenario: Every question in a turn is reconstructed

- **GIVEN** an exchange holding three answered human input requests
- **WHEN** the conversation is reloaded from history
- **THEN** all three questions and all three answers are reconstructed and correctly
  paired

#### Scenario: The unanswered question is the pending one

- **GIVEN** an exchange holding two answered requests and a third still unanswered
- **WHEN** the conversation is reloaded
- **THEN** only the third is offered as answerable, carrying the identity needed to
  resume it

#### Scenario: A legacy exchange keeps pairing by position

- **GIVEN** an exchange persisted before this change, with one request and one response
  carrying no `occurrence_id`
- **WHEN** it is reconstructed
- **THEN** the pair is preserved as it is today
