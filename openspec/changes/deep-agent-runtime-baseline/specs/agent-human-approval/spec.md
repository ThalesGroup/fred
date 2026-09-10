## Purpose

Defines how a tool call is gated behind a human approval decision, using one gate mechanism and one
resume contract shared across the runtimes that support it. `GraphRuntime` keeps its own separate
HITL lifecycle and is outside this capability's scope.

## ADDED Requirements

### Requirement: A capability-declared approval binding gates a tool call on ReAct and Deep

When an agent's selected capability declares an approval binding for a tool, and that binding's
condition applies on the current turn, the runtime SHALL pause before executing that tool call and
wait for a human decision. This SHALL hold identically whether the agent uses the ReAct runtime or
the Deep agent runtime, through one shared gate mechanism — no runtime introduces its own,
independent approval mechanism.

#### Scenario: A binding whose condition does not apply proceeds without pausing

- **GIVEN** an agent with a capability-declared approval binding on a tool
- **AND** that binding's condition does not apply on this turn
- **WHEN** the agent calls that tool, on either the ReAct or the Deep runtime
- **THEN** the call executes without pausing for a human decision

#### Scenario: A binding whose condition applies pauses and resumes on approval

- **GIVEN** an agent with a capability-declared approval binding on a tool
- **AND** that binding's condition applies on this turn
- **WHEN** the agent calls that tool, on either the ReAct or the Deep runtime
- **THEN** the turn pauses and an `AwaitingHumanRuntimeEvent` carrying a `HumanInputRequest` is
  emitted
- **AND** resuming with a proceed decision executes the tool call exactly once and the turn
  continues

#### Scenario: A binding whose condition applies pauses and skips the call on rejection

- **GIVEN** an agent with a capability-declared approval binding on a tool
- **AND** that binding's condition applies on this turn
- **WHEN** the agent calls that tool, on either the ReAct or the Deep runtime
- **THEN** the turn pauses and an `AwaitingHumanRuntimeEvent` carrying a `HumanInputRequest` is
  emitted
- **AND** resuming with a cancel decision skips the tool call entirely and lets the agent continue
  without having executed it

### Requirement: An operator-configured approval policy gates a tool call on ReAct and Deep

When an operator-configured tool-approval policy names a tool, the runtime SHALL pause before
executing a call to that tool and wait for a human decision, through the same gate mechanism a
capability-declared binding uses. This SHALL hold identically on the ReAct runtime and the Deep
agent runtime.

#### Scenario: A named tool call pauses and resumes on approval

- **GIVEN** an operator-configured approval policy names a tool
- **WHEN** the agent calls that tool, on either the ReAct or the Deep runtime
- **THEN** the turn pauses and an `AwaitingHumanRuntimeEvent` carrying a `HumanInputRequest` is
  emitted
- **AND** resuming with a proceed decision executes the tool call exactly once and the turn
  continues

#### Scenario: A named tool call pauses and skips the call on rejection

- **GIVEN** an operator-configured approval policy names a tool
- **WHEN** the agent calls that tool, on either the ReAct or the Deep runtime
- **THEN** the turn pauses and an `AwaitingHumanRuntimeEvent` carrying a `HumanInputRequest` is
  emitted
- **AND** resuming with a cancel decision skips the tool call entirely

#### Scenario: A tool outside the operator's list is unaffected

- **GIVEN** an operator-configured approval policy that does not name a tool
- **AND** that tool has no capability-declared approval binding either
- **WHEN** the agent calls that tool, on either the ReAct or the Deep runtime
- **THEN** the call executes without pausing for a human decision

### Requirement: Capability and operator approval share one gate and one resume contract

Both capability-declared and operator-configured approval SHALL resolve through the same gate and
resume through the same `HumanInputRequest` proceed/cancel contract, on both the ReAct and the Deep
runtime. Neither approval source, and neither runtime, SHALL introduce a second, incompatible
approval or resume mechanism.

#### Scenario: Both approval sources compose without a double gate

- **GIVEN** an agent where a tool is named both by a capability-declared binding and by the
  operator's approval policy
- **WHEN** the agent calls that tool
- **THEN** exactly one pending human decision is raised for that call
- **AND** resuming it resolves both sources at once, not one gate per source
