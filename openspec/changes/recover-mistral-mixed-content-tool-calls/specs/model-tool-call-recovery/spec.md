## Purpose

Defines the narrow conditions under which provider-encoded assistant content can be treated as an intended tool call, while preserving normal tool controls and preventing call syntax from appearing as the user's answer.

## ADDED Requirements

### Requirement: Recover complete Mistral calls from typed and mixed content

The runtime SHALL convert a completed Mistral assistant response into native tool calls only when an exact empty `reference` sentinel separates a currently registered tool name from complete JSON object arguments accepted by that tool's input schema. Adjacent text blocks and plain string fragments SHALL be interpreted in their original order, including when a tool name or JSON argument is split across fragments. Recovery SHALL be bounded and SHALL occur once per completed message. A later exact sentinel MAY separate another registered tool name from its arguments, provided the whole call sequence validates before any call is reconstructed.

#### Scenario: Mixed fragments encode two valid calls

- **WHEN** a Mistral response contains text blocks and plain strings that together form a registered tool name, the exact empty sentinel, and two complete valid calls
- **THEN** the runtime emits two native tool calls with the validated arguments, once each
- **AND** it continues the agent loop using their tool results

#### Scenario: Repeated exact markers encode valid calls

- **WHEN** a Mistral response contains several exact empty sentinels, each immediately following a registered tool name and preceding valid JSON arguments
- **THEN** the runtime emits each validated call once and continues with paired tool results

#### Scenario: Existing native call

- **WHEN** a response already carries native tool calls and mixed content containing the exact sentinel
- **THEN** the runtime preserves those calls and their IDs without reconstructing duplicates
- **AND** pending encoded call text does not appear in assistant or Planning events

### Requirement: Ambiguous content does not gain tool authority

The runtime MUST leave ordinary prose or quoted examples without the exact typed sentinel, literal exporter placeholders, unknown tool names, non-empty or modified reference blocks, malformed JSON, schema-invalid arguments, and over-limit representations non-executable. Non-Mistral responses MUST NOT use this recovery path.

#### Scenario: Marker or arguments are invalid

- **WHEN** a mixed-content response lacks the exact sentinel or contains invalid arguments
- **THEN** no tool call is reconstructed from that response

#### Scenario: A later marker is invalid

- **WHEN** a later marker lacks a registered tool name, is adjacent to another marker, or precedes invalid arguments
- **THEN** no call is reconstructed from the response

#### Scenario: Other provider emits similar text

- **WHEN** a non-Mistral response contains text resembling the recoverable representation
- **THEN** no tool call is reconstructed from that text

### Requirement: Stream and execute recovered calls through normal controls

The runtime SHALL keep the marker and recoverable call syntax out of assistant answer and reasoning events while the completed Mistral response is being resolved. A recovered call MUST pass the same access, human approval, budget, tracing, observability, and result-pairing controls as a native call. Text that is not part of a recovered call SHALL remain visible through the existing assistant or thought routing.

#### Scenario: Recovered call completes

- **WHEN** a completed mixed-content representation is recovered
- **THEN** the user sees the subsequent answer and normal tool trace, without the marker or encoded call syntax in the answer
- **AND** the call passes the existing gates and has a paired tool result

#### Scenario: Ordinary streamed response

- **WHEN** a Mistral response has ordinary text or an unrecognized typed block and no recoverable complete call
- **THEN** the text remains visible in the assistant answer without being executed
