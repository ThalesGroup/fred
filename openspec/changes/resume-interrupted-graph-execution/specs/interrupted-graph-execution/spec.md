## Purpose

Lets a Graph agent execution that was cut short by a lost process be continued from its
last persisted step, by an explicit user choice, instead of being silently restarted
from the beginning.

## ADDED Requirements

### Requirement: Step state is persisted before the next step starts

For a Graph agent, the runtime SHALL persist each completed step's state before it
starts the next step. No step SHALL run while the state produced by the step before it
is not yet persisted.

#### Scenario: Persistence of a step blocks the next step
- **WHEN** a Graph step completes and the persistence of its state is still in progress
- **THEN** the next step has not started
- **AND** it starts only once that persistence has completed

#### Scenario: Failed persistence stops the run
- **WHEN** persisting a completed step's state fails
- **THEN** the next step does not run
- **AND** the run ends with an execution error

### Requirement: External effects remain the agent author's responsibility

Checkpoint persistence and an external operation are not one atomic transaction. The
runtime SHALL NOT promise exactly-once external effects. A continued step may execute
again from its beginning even if an external operation already committed. The agent
author MUST make replayable external operations idempotent or reconcile their outcome,
using the same operation identity and content prepared in an earlier persisted step.
An operation that cannot safely be repeated or reconciled MUST NOT be blindly retried.
Completed LangGraph task results SHALL remain available on continuation; recovery SHALL
NOT discard them merely to obtain a new admission identity.

#### Scenario: External commit succeeds before the process is lost
- **WHEN** an external operation commits and the process dies before its result is persisted
- **THEN** continuation may execute the interrupted step again
- **AND** the agent's adapter is responsible for safely replaying or reconciling the same operation
- **AND** the runtime does not infer that the external operation failed

### Requirement: Only a lost process leaves an interrupted execution

A Graph execution SHALL be interrupted when its persisted state still has steps to run,
no human input is pending, and no live process ended the run. A run that ends in a live
process SHALL leave no interrupted execution behind. This covers success, an unhandled
node failure, the step limit and an internal error. A run ended by cancellation or a
client disconnect SHALL keep its pending step, so that it remains continuable.

#### Scenario: Process lost during a step
- **WHEN** the process running a Graph execution dies after step N was persisted and before the execution completed
- **THEN** the execution is interrupted, with step N+1 as its interrupted step

#### Scenario: Node failure is a normal terminal failure
- **WHEN** a Graph node raises an unhandled error and the run ends in the same live process
- **THEN** the execution is not interrupted
- **AND** the user's next message starts a new turn exactly as before this change

#### Scenario: Step limit is a normal terminal failure
- **WHEN** a Graph execution stops because it reached its step limit
- **THEN** the execution is not interrupted

#### Scenario: Pending human input is not an interruption
- **WHEN** a Graph execution is paused on a human-in-the-loop request
- **THEN** it is not reported as interrupted
- **AND** the existing human-in-the-loop behaviour applies unchanged

### Requirement: A new turn does not silently replace an interrupted execution

When a new turn targets a Graph agent conversation whose execution is interrupted, and
the request carries no `interrupted_action`, the runtime SHALL NOT start the turn. It
SHALL first complete the existing authentication and authorization checks. It SHALL then
answer with one `execution_interrupted` event and end the response. The event SHALL
carry a human-input request with stage `execution_interrupted`, a title naming the
interrupted step, and the choices `continue` and `restart`. It SHALL also carry an
opaque `interruption_id` that identifies this interruption. This outcome SHALL write no
conversation history and no turn KPI. The event SHALL expose no state content other
than the interrupted step's identity.

#### Scenario: New message after a crash
- **WHEN** an authorized user sends a new message to a conversation whose Graph execution is interrupted
- **THEN** the response contains exactly one `execution_interrupted` event offering `continue` and `restart`
- **AND** no step of the agent runs and no history row is written

#### Scenario: Unauthorized caller learns nothing
- **WHEN** a caller who is not authorized for the conversation sends a turn to it
- **THEN** the request is rejected by the existing authorization checks
- **AND** no `execution_interrupted` event is emitted

### Requirement: Continue resumes the interrupted step without repeating completed steps

A request with `interrupted_action` set to `continue` and the current `interruption_id`
SHALL resume the interrupted execution at its interrupted step. It SHALL use the
persisted state and SHALL run no completed step again. The request SHALL NOT require
user input. The continued run SHALL stream and complete like an ordinary turn, and
SHALL persist its assistant output as a new exchange without a fabricated user row.

#### Scenario: Continue after a process restart
- **WHEN** the process dies after step N was persisted, a new process starts on the same persistent storage, and the user chooses `continue`
- **THEN** execution resumes at step N+1 with the state persisted by step N
- **AND** steps 1 to N are not executed again

#### Scenario: Continue re-runs only the interrupted step
- **WHEN** the process died while running step N+1, and the user chooses `continue`
- **THEN** step N+1 runs again from its beginning with the same persisted input state

### Requirement: Continue excludes concurrent attempts and survives owner loss

The runtime SHALL admit at most one live `continue` per interruption, across processes
and replicas. A concurrent `continue` for the same interruption SHALL be refused. Loss
of the admitted process before the interrupted step completes SHALL NOT permanently
consume the right to continue from that checkpoint. Another authorized process SHALL
be able to continue the same persisted step without restarting completed preparation
or requiring direct database intervention. Elapsed time alone SHALL NOT establish that
a live owner has stopped. Ordinary HITL single-use admission SHALL remain unchanged. A
`continue` whose `interruption_id` does not identify the conversation's current
interruption SHALL be rejected with an execution error, and no step SHALL run. This
covers an execution that already advanced, completed, was restarted, or was never
interrupted.

#### Scenario: Two simultaneous continues
- **WHEN** two `continue` requests for the same interruption arrive concurrently
- **THEN** exactly one runs the interrupted step
- **AND** the other is refused as already being resumed

#### Scenario: The continuing process dies in the same step
- **WHEN** a continuation is admitted and its process dies before the interrupted step completes
- **THEN** another authorized process can continue that step from the same persisted state
- **AND** completed preparation is not repeated and no claim needs manual deletion

#### Scenario: A long-running continuation still owns admission
- **WHEN** an admitted continuation remains live in a step longer than an admission timeout
- **THEN** elapsed time does not authorize another continuation of that interruption

#### Scenario: Stale interruption
- **WHEN** a `continue` carries an `interruption_id` from an interruption that has since been continued past or restarted
- **THEN** the request is rejected with an execution error and no step runs

#### Scenario: Continue on an agent with nothing to continue
- **WHEN** a `continue` targets a conversation with no interrupted Graph execution, or a non-Graph agent
- **THEN** the request is rejected with an execution error and no step runs

### Requirement: Restart starts a new turn

A request with `interrupted_action` set to `restart` and user input SHALL run as an
ordinary new turn, with today's behaviour. It SHALL replace the interrupted execution.
On a conversation without an interrupted execution, and on non-Graph agents, `restart`
SHALL have no effect beyond running the turn normally.

#### Scenario: Restart after a crash
- **WHEN** the user chooses `restart` for an interrupted execution and sends their message
- **THEN** a new turn runs from the agent's entry step with the new message

#### Scenario: Restart on an ordinary conversation
- **WHEN** a request with `restart` targets a conversation without an interrupted execution
- **THEN** the turn runs exactly as a request without `interrupted_action`

### Requirement: The chat offers continue or restart with the human-input card

The chat UI SHALL render an `execution_interrupted` event with the same card component
it uses for human-input requests. It SHALL show the request's title, question and
choices. It SHALL restore the user's unsent message into the composer. Choosing
`continue` SHALL send a continue request with the received `interruption_id`. Choosing
`restart` SHALL send the restored message with `restart`. After the user stops a turn
with the Stop control, the next message in that conversation SHALL be sent with
`restart`, so that a deliberate stop is never offered as continuable.

#### Scenario: Card and draft restore
- **WHEN** the chat receives an `execution_interrupted` event in response to a message
- **THEN** it shows the card with `continue` and `restart`
- **AND** the message the user had sent is back in the composer

#### Scenario: Stop then a new message
- **WHEN** the user stops a running Graph turn with the Stop control and then sends a new message
- **THEN** the message is sent with `restart` and no interruption card is shown
