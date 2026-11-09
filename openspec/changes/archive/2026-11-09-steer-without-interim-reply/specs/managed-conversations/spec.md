# Spec Delta

## MODIFIED Requirements

### Requirement: In-thread messages reach a safe model boundary

The runtime SHALL deliver each eligible update once to the active ReAct or Deep agent after dispatched tool results and before the next model decision. Delivery SHALL persist a canonical rank and clear pending state independently of model output. Rank-ordered history SHALL keep tool call/result groups intact. The agent SHALL apply updates in order and answer outstanding questions in its ordinary final response. Updates missing a boundary SHALL remain pending for the next eligible turn.

#### Scenario: Delivery after tool results

- **GIVEN** a tool batch is running when the user submits a message
- **WHEN** all dispatched results are available and the agent resumes model work
- **THEN** the agent receives the message once after those results
- **AND** its definitive rank places it after the completed tool batch in reloaded history
- **AND** the pending clock disappears before the next model decision

#### Scenario: Two updates before a model decision

- **GIVEN** two updates are submitted while a tool batch is running
- **WHEN** the agent resumes model work
- **THEN** both messages are delivered once in submission order
- **AND** the next model decision can call tools without first producing an assistant reply
- **AND** the final response accounts for both updates

#### Scenario: Slow preparation of the first update

- **GIVEN** the user sends two updates to the same active session in order
- **WHEN** preparation of the first request takes longer than the interval between sends
- **THEN** both messages appear immediately in send order
- **AND** their persisted provisional ranks and model delivery retain that order after reload
- **AND** a definitely rejected first submission does not prevent the second from being sent
- **AND** an uncertain first POST prevents later submissions from overtaking it until its identity is resolved

#### Scenario: First-turn steering belongs to its agent instance

- **GIVEN** a managed agent starts the first turn in a new session
- **WHEN** a user submits an update before that turn finishes
- **THEN** its opening user message already identifies the session's agent instance in shared history
- **AND** an update naming another instance is rejected without creating a pending clock
- **AND** only the owning instance can incorporate and deliver the update

#### Scenario: Progress question during a long task

- **WHEN** the user asks for progress while a turn is active
- **THEN** the message is delivered at the next eligible boundary without requiring an immediate assistant reply
- **AND** the ordinary final response addresses the question if it remains relevant

#### Scenario: Checkpoint precedes delivery

- **GIVEN** an update reaches a ReAct or Deep model boundary
- **WHEN** the runtime promotes the update in shared history
- **THEN** the graph checkpoint already contains that user message under its stable identity
- **AND** a failed promotion leaves the update pending and prevents the model call
- **AND** a later boundary can retry promotion without injecting the message twice

#### Scenario: Concurrent delivery from two exchanges

- **GIVEN** two runtime replicas read the same pending update
- **WHEN** one exchange delivers it first
- **THEN** another exchange SHALL NOT claim or process the same update
- **AND** a retry in the owning exchange retains the original rank

#### Scenario: Delivery fails

- **GIVEN** an update is waiting at a model boundary
- **WHEN** the runtime cannot persist its delivery
- **THEN** the message remains pending with its clock and the model does not proceed with that update

#### Scenario: End before another model call

- **GIVEN** a submitted message is still pending
- **WHEN** the active turn ends without another model decision
- **THEN** the message remains visible and is submitted as the next ordinary turn

#### Scenario: A newer command while an older update is pending

- **GIVEN** an update missed the active turn and remains pending
- **WHEN** the user tries to start a new ordinary turn through the composer, a command, a skill, or the execution API
- **THEN** the oldest pending update opens the next turn first
- **AND** the newer turn cannot overtake it in model context
- **AND** the execution API reports HTTP 409 before opening a stream

#### Scenario: Opening identity cannot accompany a resume

- **WHEN** a caller combines a pending message identity with a human-input resume or interruption action
- **THEN** the request is rejected before execution
- **AND** the pending clock is not cleared without the model receiving that message

#### Scenario: Graph interruption recovery with an update pending

- **GIVEN** a Graph turn is interrupted while a user update is pending
- **WHEN** the user continues or restarts the interrupted work
- **THEN** recovery is allowed for the same agent instance without promoting the update
- **AND** the pending update retains its identity and opens the next eligible ordinary turn

#### Scenario: Human-input pause and another pod

- **GIVEN** a message is submitted during a turn that pauses for human input
- **WHEN** the user answers and another runtime replica resumes the turn
- **THEN** the message remains pending until the resumed agent reaches its next safe model boundary
- **AND** it is incorporated once with the same message identity

#### Scenario: Graph fallback pauses for human input

- **GIVEN** a pending message starts the next ordinary Graph turn
- **WHEN** Graph reaches a human-input pause before a final answer
- **THEN** the message receives its definitive opening rank and no longer appears pending

## REMOVED Requirements

### Requirement: In-progress updates receive separate assistant replies

**Reason**: Steering now guides the ordinary ongoing turn and its final response; a forced assistant reply added latency and coupled delivery to model output.

**Migration**: Existing assistant replies remain readable in conversation history. New updates are delivered independently and do not produce interim replies.
