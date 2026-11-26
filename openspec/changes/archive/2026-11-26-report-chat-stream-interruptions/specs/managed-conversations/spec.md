## ADDED Requirements

### Requirement: Managed chat explains an unexpected stream interruption

The managed chat SHALL display one localized connection-interruption message in the active English or French locale when a live turn encounters an unexpected failure opening or reading its SSE stream, or the stream closes without a recognized terminal event. The message SHALL omit raw transport error text. The chat SHALL retain the existing behavior for an intentional abort, a superseded view, an HTTP rejection and an explicit runtime terminal event. An interrupted turn SHALL NOT be replayed automatically.

#### Scenario: Connection fails before the first frame

- **WHEN** the active browser request fails at the transport before receiving any chat event
- **THEN** the chat displays the localized interruption message once

#### Scenario: A response ends without a terminal event

- **WHEN** the SSE stream closes or fails during an active send or an accepted human-input resume without a terminal event
- **THEN** the chat displays the localized interruption message and continues to treat the turn as incomplete

#### Scenario: A terminal event or local Stop already settled the response

- **WHEN** the user deliberately stops the turn or the browser has already processed a terminal event before the stream closes
- **THEN** the chat does not display a connection-interruption message

### Requirement: An early downstream disconnect releases the turn's provider stream

When the runtime detects that an active managed chat response has lost its downstream connection before a terminal event, it SHALL cancel the affected turn's model streaming work and await the release of that turn's provider HTTP resources during response cleanup. Existing run and checkpoint cleanup SHALL complete, and unrelated turns SHALL continue using the shared HTTP client. The runtime SHALL NOT retry an invocation cancelled for this reason.

#### Scenario: The provider has yet to return response headers

- **WHEN** the chat connection closes while Fred awaits the provider's response headers
- **THEN** Fred stops waiting for that model response and completes the cancelled turn's cleanup

#### Scenario: A provider stream is already open

- **WHEN** the chat connection closes while Fred reads a provider stream or writes an outgoing chat frame
- **THEN** Fred closes that turn's provider response and completes cleanup without retrying the invocation
- **AND** another turn using the same client can continue its own model call

### Requirement: Conversation Traces distinguishes Stop from an unexpected chat disconnect

For a captured managed chat stream, Conversation Traces SHALL show a localized Stop requested result when its early disconnect matches an explicit Stop signal from the conversation owner. It SHALL show Stream interrupted for a confirmed early downstream disconnect without that signal. Stop SHALL still close the stream immediately and settle the chat silently.

#### Scenario: A user clicks Stop on an active stream

- **WHEN** the conversation owner explicitly stops a captured stream before a terminal result
- **THEN** the resulting catalog and turn detail display Stop requested even if the browser has yet to receive response headers or the signal arrives after the disconnect facts

#### Scenario: The connection fails without a Stop request

- **WHEN** Fred observes a downstream disconnect on a captured stream before a terminal result without a matching Stop signal
- **THEN** the catalog and turn detail display Stream interrupted

#### Scenario: A stop signal arrives for a previous or completed segment

- **WHEN** a Stop signal arrives after the turn completes or after a different segment establishes the current turn result
- **THEN** the established result remains authoritative and resumable turns can accept later segments
