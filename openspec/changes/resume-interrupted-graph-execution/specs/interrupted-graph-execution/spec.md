## Purpose

Preserve prepared Graph work and let an authorized user explicitly continue an
unfinished execution, with safe external replay owned by the agent's adapter and
one active execution per conversation as the supported usage contract.

## ADDED Requirements

### Requirement: Preparation is durable before the next step

The runtime SHALL persist completed Graph step state before starting the next step.
Persistence failure SHALL prevent that next step from running.

#### Scenario: Preparation cannot be persisted
- **WHEN** persistence of prepared operation content and identity is blocked or fails
- **THEN** the publication step does not start before persistence succeeds
- **AND** failed persistence reports an error without dispatching publication

### Requirement: Unfinished work is preserved without diagnosing process death

Pending non-HITL work SHALL be presented as unfinished, not proof of a dead owner or
failed external operation. The runtime SHALL NOT automatically erase its continuation
point because a node failed, a step limit was reached or a stream was cancelled.
Known errors SHALL remain errors, with no automatic continuation.

#### Scenario: Publication times out after the destination commits
- **WHEN** a publication step reports a timeout after the destination accepted it
- **THEN** the runtime reports the error and preserves the recorded preparation
- **AND** it does not infer that the external publication failed or retry automatically

#### Scenario: Failure or step limit leaves pending work
- **WHEN** an execution ends with an error or step limit and its saved state has pending steps
- **THEN** a later authorized request identifies the work as unfinished
- **AND** the runtime does not silently replace it with a new turn

### Requirement: Discovery and continuation use current authority and identity

The runtime SHALL authorize discovery and continuation against the current conversation
and agent binding before exposing unfinished work or running a node. Discovery SHALL
return `execution_interrupted` with an opaque current `interruption_id` and the pending
step identity, without executing a step or creating a fictitious history row.
Continue SHALL require that identity, empty input and no HITL resume payload.

#### Scenario: Unauthorized or stale continuation
- **WHEN** a caller lacks current authority or supplies a stale interruption identity
- **THEN** continuation is rejected without running a node
- **AND** an unauthorized caller receives no unfinished-state disclosure

#### Scenario: Continue contains a new instruction
- **WHEN** a Continue request includes non-empty input
- **THEN** it is rejected instead of ignoring and recording that instruction

### Requirement: Explicit choices preserve user intent

The chat SHALL offer Continue, Restart and Later with an explanation that a previous
external effect may already have happened. Continue SHALL preserve the draft and add
no user message. Restart SHALL explicitly start a new turn and SHALL NOT be described
as undoing previous external effects. Later SHALL run nothing and preserve saved work.

#### Scenario: User postpones recovery
- **WHEN** the user chooses Later
- **THEN** the card can close without an execution request or checkpoint mutation
- **AND** a subsequent message can rediscover the unfinished work

#### Scenario: Continuation is refused before HTTP acceptance
- **WHEN** preparation or the execution HTTP request is refused before acceptance
- **THEN** the recovery controls remain available or are restored in the active conversation
- **AND** any Stop intent awaiting a successful submission is not consumed

#### Scenario: The stream fails after acceptance
- **WHEN** the transport fails after execution was accepted
- **THEN** the client reports the interruption without automatically resubmitting work

### Requirement: Continuation preserves preparation and durable results

Continue SHALL resume saved pending work without recalculating completed preparation or
discarding persisted task results. A pending step can execute again. Agent authors MUST
persist stable operation identity and content before dispatch and provide idempotent
replay or outcome reconciliation for external operations. Runtime checkpointing SHALL
NOT be represented as an exactly-once external delivery guarantee.

#### Scenario: Process loss and destination response loss
- **WHEN** a process dies after preparation and a publication has committed without a durable receipt
- **THEN** an explicitly continued run uses the same prepared identity and content
- **AND** an idempotent reference destination records one business publication

#### Scenario: Result persistence fails
- **WHEN** an external acknowledgement arrives but its checkpoint cannot be persisted
- **THEN** the run does not report crash-safe completion
- **AND** later explicit recovery replays or reconciles the same prepared operation

#### Scenario: Receipt is durable and finalization is interrupted
- **WHEN** the publication result was persisted before finalization was interrupted
- **THEN** continuation finalizes without another publication call

#### Scenario: Destination cannot safely replay or reconcile
- **WHEN** an operation has an uncertain outcome and its destination cannot replay or reconcile it
- **THEN** the agent author must require external verification rather than blindly repeat it
- **AND** generic user confirmation does not establish an external outcome

### Requirement: Admission has bounded scope and complete local teardown

Supported use SHALL require one active execution per Graph conversation. Concurrent
ordinary turns/Restart, partitions and late writers are outside this guarantee.
Technical continuation SHALL retain supported provider admission, reject a competing
continuation while held and await local engine teardown before releasing admission.
Unsupported providers SHALL reject continuation without an unguarded fallback.

#### Scenario: Close during a progress event
- **WHEN** a consumer closes a continuation stream while its node is still active
- **THEN** local engine task teardown completes before continuation admission is released

#### Scenario: Owner process ends
- **WHEN** a continuing process exits and its provider releases ownership
- **THEN** an explicit continuation can acquire admission without deleting a permanent claim
- **AND** this does not imply that an earlier external operation had no effect

### Requirement: Ordinary HITL and other engines retain their contracts

Ordinary human-input pauses SHALL retain their existing resume semantics. ReAct and
Deep SHALL reject technical Continue and otherwise retain existing behavior. Documented
non-interactive Graph callers SHALL retain their restart behavior.

#### Scenario: A human-input pause is pending
- **WHEN** a Graph checkpoint is waiting for a human answer
- **THEN** the ordinary HITL path is used instead of the unfinished-execution choice
