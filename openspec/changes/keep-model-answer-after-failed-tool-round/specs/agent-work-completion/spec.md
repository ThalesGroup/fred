## ADDED Requirements

### Requirement: A model answer after a failed tool round is the final response

The ReAct runtime SHALL use the model's own non-empty answer, produced after a round in
which every tool call failed, as the final response, and SHALL stream that answer's
deltas. The failed calls SHALL remain marked as errors on their tool-result events. The
runtime SHALL fall back to the failed round's user-facing error text only when the model
produced no non-empty answer after the failure.

#### Scenario: Tool-call cap refusal followed by a model answer

- **GIVEN** the per-turn tool-call cap refuses a call with an error-status tool message
  and no Fred artifact
- **WHEN** the model then ends the turn with its own answer
- **THEN** the final event contains that answer and the refused call's tool-result event
  is marked as an error

#### Scenario: Typed tool error followed by a model answer

- **GIVEN** a tool returns a typed `is_error == true` result for every call of a round
- **WHEN** the model then ends the turn with its own answer
- **THEN** the final event contains that answer, not the tool's error text

#### Scenario: No model answer after a failed round

- **GIVEN** every call of the last tool round failed
- **WHEN** the model ends the turn with an empty answer
- **THEN** the final event contains the failed call's user-facing error text

#### Scenario: Answer deltas stream after a failed round

- **GIVEN** every call of a round failed
- **WHEN** the model streams answer text afterwards
- **THEN** the runtime emits that text as assistant deltas

## MODIFIED Requirements

### Requirement: Untrusted tool failures never expose provider detail

The runtime SHALL expose only a bounded Fred-owned message for an untyped failure or a
runtime-provider/MCP error. Provider-controlled content, blocks, sources, UI parts,
exception representations, paths, URLs, tokens, and wrapper instructions SHALL NOT enter
user-facing error events.

#### Scenario: Untyped exception text becomes a generic message

- **GIVEN** a failed tool message contains a secret or path in raw wrapper content and no
  Fred error artifact
- **WHEN** ReAct emits the tool-result event, and the final event without a model answer
  after the failure
- **THEN** both contain only the bounded generic failure message

#### Scenario: Provider tuple error is sanitized before binding

- **GIVEN** a runtime provider returns paired content and an `is_error == true` artifact
  containing provider-controlled blocks, sources, and UI parts
- **WHEN** Fred resolves that provider tool
- **THEN** it replaces both values with a generic Fred-owned error result before binding

#### Scenario: Fred-owned typed errors retain useful text

- **GIVEN** a Fred-owned tool returns a typed user-facing error artifact
- **WHEN** ReAct reports that failure
- **THEN** the tool-result event, and the final event when it falls back to the error,
  contain the artifact's rendered text without Fred's internal presentation prefix
