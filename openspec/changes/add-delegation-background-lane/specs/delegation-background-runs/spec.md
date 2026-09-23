## Purpose

Defines what happens to a run when the person leaves, and how work that is meant
to run without the person is admitted, executed, made visible and cancelled.

## ADDED Requirements

### Requirement: Foreground runs are bound to their stream

A foreground run SHALL be cancelled, with its children, after a reconnect grace
once its stream has closed. A dropped connection SHALL NOT convert a foreground
run into background work. The grace SHALL be configurable with a default of 60 s;
the original wall-clock ceiling SHALL continue to apply while disconnected.

#### Scenario: Stream closes past the grace

- **GIVEN** a foreground run whose stream closes
- **WHEN** the grace elapses without a reconnect
- **THEN** the run ends with reason `cancelled` and its children are cancelled

### Requirement: Reconnection attaches to the same authorized run

The existing execution-stream endpoint SHALL accept a reconnect request naming
the server-issued run handle and optional last received event sequence, mutually
exclusive with a new execution request. The initial response SHALL expose that
handle and each streamed event SHALL expose its sequence as an SSE id. The runtime
SHALL authenticate the current person, require the recorded owner and current
standing/agent/team permission, and allow only one attachment. A reconnect within
grace on the admitting pod SHALL replay buffered events after the cursor and then
stream live, without new execution, repeated tools, re-registration, changed
attribution or a reset budget. Replay storage SHALL be bounded.

#### Scenario: Owner reconnects within grace

- **GIVEN** an owner who has received the run handle and an event sequence
- **WHEN** the stream disconnects and they reconnect to the admitting pod within
  grace with their current token and that cursor
- **THEN** they receive later buffered events followed by live events from the
  same run, no tool repeats, and its original deadline is unchanged

#### Scenario: Reconnect reaches another replica

- **GIVEN** a run whose state exists only on its admitting pod
- **WHEN** a reconnect reaches a replica without that run
- **THEN** it returns 404, starts no execution and performs no control-plane lookup;
  the original run's grace and ceiling remain unchanged

#### Scenario: Another person attempts attachment

- **WHEN** another authenticated person presents the handle of an existing run
- **THEN** attachment is refused with 403 without altering or cancelling that run

#### Scenario: Owner loses authority before reconnect

- **WHEN** the owner reconnects but no longer has standing or the required permission
- **THEN** attachment is refused with 403 and the run and its children end for lost authority

#### Scenario: Replay is unavailable

- **WHEN** the authorized owner requests events that the bounded buffer no longer
  retains or supplies a cursor beyond the emitted sequence
- **THEN** reconnect returns 409 without attaching, emitting partial replay,
  extending grace or starting a replacement execution

#### Scenario: Reconnect after grace

- **WHEN** the owner reconnects to a known run already cancelled after grace
- **THEN** reconnect returns 410 and the client does not automatically start a new run

#### Scenario: Competing attachments

- **WHEN** two authorized reconnects compete for a detached run
- **THEN** only one attaches and receives replay/live events; the other is refused
  without cancelling the run or changing the successful attachment

#### Scenario: Resume after a long human pause

- **GIVEN** a run paused for human input whose stream closed past the grace
- **WHEN** the person resumes
- **THEN** the resume is admitted as a new run with the person's current token
  and no execution/tool/data call is made for the cancelled run; only its terminal
  lifecycle report is permitted

### Requirement: Background work is explicitly admitted

A background run SHALL be started only through an explicit request by a person
who may use the agent in that team, and SHALL be recorded durably by the platform
with the person, roles, team, agent, prompt, scope and mode.

#### Scenario: Start without the agent permission

- **WHEN** a person without permission to use the agent starts a background run
- **THEN** the request is refused and no record is written

### Requirement: Execution re-checks and fails closed

Before executing a background run the platform SHALL re-check the recorded
person's standing and permission and SHALL refuse to run if either fails. It SHALL
register the execution using its own workload bearer under the foundation's
lifecycle-report contract, without requiring a person token or active session,
and SHALL refuse execution if registration fails.

#### Scenario: Permission removed before execution

- **GIVEN** a recorded background run
- **WHEN** the person's permission is removed before it executes
- **THEN** the run is refused and recorded as failed for lost authority

#### Scenario: Start after the person's session ends

- **GIVEN** an explicitly admitted durable task whose person still has standing and permission
- **WHEN** the scheduler starts it after the person's session has ended
- **THEN** it registers and executes using the runtime's workload bearer and the
  recorded person, with no person credential or receiver registry lookup

### Requirement: Background calls name the recorded person

Calls made for a background run SHALL carry grant parameters naming the recorded
person, the run's record SHALL carry `mode = background`, audit events SHALL name
that mode, and the run SHALL execute under its own budget.

#### Scenario: Background call

- **WHEN** a background run calls a receiver
- **THEN** the grant parameters name the recorded person and the audit event
  names the background mode

### Requirement: Schedules re-check every tick

A scheduled run SHALL require an explicit opt-in at creation and SHALL perform
the execution re-check at every tick.

#### Scenario: Standing removed between ticks

- **WHEN** the recorded person loses standing before the next tick
- **THEN** that tick does not execute

### Requirement: Visibility and cancellation

A person SHALL be able to list and cancel their own background and scheduled
runs; a team admin SHALL be able to list and cancel the team's. Cancellation SHALL
reach the executing worker and its children.

#### Scenario: Team admin cancels

- **WHEN** a team admin cancels a background run in their team
- **THEN** the worker stops the run and its children and the task is recorded as
  cancelled

### Requirement: Agent-run worker startup requires explicit opt-in

The pod SHALL start an agent-run worker only when `scheduler.agent_runs_enabled`
is true. The setting SHALL default to false independently of `scheduler.enabled`.
Explicit opt-in SHALL fail startup when the enabled Temporal scheduler, delegation,
standing or control-plane prerequisites are missing.

#### Scenario: Existing generic scheduler configuration

- **GIVEN** the generic scheduler is enabled and delegation is disabled
- **WHEN** the pod starts without agent-run worker opt-in
- **THEN** startup preserves existing behavior without starting an agent-run worker

#### Scenario: Explicit worker opt-in lacks prerequisites

- **WHEN** the agent-run worker is explicitly enabled without its required configuration
- **THEN** startup fails before connecting a partially configured worker

### Requirement: Durable admission and cancellation survive interleavings

Background, schedule and occurrence admission SHALL serialize a fresh standing
check and private-state persistence with account deletion. Personal-team access
SHALL NOT bypass standing. Cancellation before workflow binding SHALL persist its
intent and be delivered when the execution becomes available. Retrying an existing
occurrence SHALL repair its missing binding without recreating a purged task or
resetting terminal state.

#### Scenario: Account is deleted while admission waits

- **GIVEN** background admission has started but has not persisted its private state
- **WHEN** deletion purges that person's records first
- **THEN** admission is denied without recreating a task, prompt or schedule

#### Scenario: Cancellation arrives while dispatch is pending

- **GIVEN** an owner-visible agent-run task whose workflow dispatch has not returned
- **WHEN** the owner cancels and the task service later binds the execution
- **THEN** the durable cancellation intent causes that execution to be cancelled,
  including when binding is recovered by a fresh service instance

#### Scenario: Scheduled occurrence retries after binding failure

- **GIVEN** occurrence admission was saved but execution binding failed
- **WHEN** the same occurrence is retried
- **THEN** it repairs the existing binding before success and subsequent cancellation
  reaches the actual execution without creating a second task

### Requirement: Task completion waits for runtime cleanup

The background execution adapter SHALL await closure of its runtime event iterator
in the consuming task before terminal task reporting or activity completion. This
SHALL apply to final, error, human-pause and cancellation paths.

#### Scenario: A terminal event precedes delayed cleanup

- **GIVEN** a runtime iterator emits a terminal event then performs delayed cleanup
- **WHEN** the activity stops consuming the iterator
- **THEN** run-scope and lifecycle cleanup finish before terminal reporting and return

#### Scenario: A scheduled occurrence is cancelled before its child starts

- **GIVEN** a scheduled parent has admitted a task but has not started its child
- **WHEN** the owner cancels that task
- **THEN** cancellation targets the existing parent and prevents child execution;
  if the child already started, the parent awaits its cancellation cleanup
