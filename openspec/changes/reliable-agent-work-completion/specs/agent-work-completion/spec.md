## Purpose

Defines the first shipped reliability boundary for agent work completion: tool failures
are reported truthfully without exposing untrusted diagnostic content.

## ADDED Requirements

### Requirement: Either tool failure signal marks the call as failed

The ReAct runtime SHALL classify a tool result as failed when either the underlying
`ToolMessage` has error status or its normalized Fred artifact reports an error.

#### Scenario: Error status without an artifact remains a failure

- **GIVEN** a tool call returns `status == "error"` without a Fred artifact
- **WHEN** ReAct emits the tool-result event
- **THEN** the event is marked as an error and the failed round cannot be finalized as a
  successful tool result

#### Scenario: Error status overrides a non-error artifact

- **GIVEN** a tool message has `status == "error"` and a present artifact has
  `is_error == false`
- **WHEN** ReAct emits the tool-result event
- **THEN** the event is still marked as an error

### Requirement: Untrusted tool failures never expose provider detail

The runtime SHALL expose only a bounded Fred-owned message for an untyped failure or a
runtime-provider/MCP error. Provider-controlled content, blocks, sources, UI parts,
exception representations, paths, URLs, tokens, and wrapper instructions SHALL NOT enter
user-facing error events.

#### Scenario: Untyped exception text becomes a generic message

- **GIVEN** a failed tool message contains a secret or path in raw wrapper content and no
  Fred error artifact
- **WHEN** ReAct emits the tool-result and final events
- **THEN** both contain only the bounded generic failure message

#### Scenario: Provider tuple error is sanitized before binding

- **GIVEN** a runtime provider returns paired content and an `is_error == true` artifact
  containing provider-controlled blocks, sources, and UI parts
- **WHEN** Fred resolves that provider tool
- **THEN** it replaces both values with a generic Fred-owned error result before binding

#### Scenario: Fred-owned typed errors retain useful text

- **GIVEN** a Fred-owned tool returns a typed user-facing error artifact
- **WHEN** ReAct reports that failure
- **THEN** both user-facing events contain the artifact's rendered text without Fred's
  internal presentation prefix
