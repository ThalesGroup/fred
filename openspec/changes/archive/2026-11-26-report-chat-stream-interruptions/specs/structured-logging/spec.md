## ADDED Requirements

### Requirement: Early managed chat stream interruption has a diagnostic event

When an active managed chat SSE response is cancelled or its downstream connection closes before a terminal event is sent, the runtime SHALL emit exactly one `chat_stream_interrupted` diagnostic. It SHALL carry the available owned request, correlation and conversation references and a bounded reason. It SHALL use `downstream_disconnect` when transport evidence establishes a disconnection and `cancelled` when only cancellation is observed. It SHALL omit request content, response content and raw exception messages.

#### Scenario: Client disconnects before the first event

- **WHEN** the peer closes a managed chat stream while the runtime is still waiting for its first event
- **THEN** the runtime emits one `chat_stream_interrupted` event with reason `downstream_disconnect` and the available correlation references

#### Scenario: Cancellation has no transport evidence

- **WHEN** an active managed chat response is cancelled before sending its terminal event and there is no observed downstream disconnect
- **THEN** the diagnostic uses reason `cancelled`

#### Scenario: A terminal event was sent

- **WHEN** a managed chat connection closes after the runtime successfully sends its terminal event
- **THEN** connection teardown does not emit a `chat_stream_interrupted` diagnostic
