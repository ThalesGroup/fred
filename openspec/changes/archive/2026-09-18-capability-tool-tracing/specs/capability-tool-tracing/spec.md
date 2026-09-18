## Purpose

Make tool execution visible and correctly parented in ReAct and Deep traces while respecting content-capture privacy controls.

## ADDED Requirements

### Requirement: One tool observation per invocation

The runtime SHALL trace middleware-contributed tools in ReAct and Deep exactly once and preserve existing binder tool spans. Each tool span SHALL attach to its active parent and become the active parent during execution.

#### Scenario: Middleware tool executes
- **WHEN** a middleware-contributed tool executes under an active agent span
- **THEN** one tool observation is created under that span and nested spans attach to the tool
- **AND** the previous parent is restored afterward

#### Scenario: Binder tool executes
- **WHEN** an already binder-traced tool passes through tool observability
- **THEN** only its binder span is created

### Requirement: Terminal outcomes and privacy

Tool spans SHALL end on success, returned error, raised exception or cancellation. Cancellation SHALL remain distinct from failure, and arguments/results SHALL be recorded only with content capture enabled.

#### Scenario: Failed or cancelled call
- **WHEN** a tool returns an error status or error artifact, raises an exception, or is cancelled
- **THEN** the ended span records error or cancelled respectively without swallowing the exception or cancellation

#### Scenario: Content capture disabled
- **WHEN** tracing is enabled with content capture disabled
- **THEN** the span contains no tool arguments or results

#### Scenario: Content capture enabled
- **WHEN** tracing and content capture are enabled
- **THEN** tool arguments and returned content are supplied to the trace backend
