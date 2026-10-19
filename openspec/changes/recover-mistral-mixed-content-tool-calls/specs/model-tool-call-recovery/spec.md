## Purpose

Defines the narrow conditions under which provider-encoded assistant content can be treated as an intended tool call, while preserving normal tool controls and preventing call syntax from appearing as the user's answer.

## ADDED Requirements

### Requirement: Recover complete Mistral calls from typed and mixed content

The runtime SHALL convert a completed Mistral assistant response into native tool calls only when an exact empty `reference` sentinel separates a currently registered tool name from complete JSON object arguments accepted by that tool's input schema. Adjacent text blocks and plain string fragments SHALL be interpreted in their original order, including when a tool name or JSON argument is split across fragments. Recovery SHALL be bounded by the recovered text size and call count, not by the number of content blocks, so a streamed response holding one block per delta remains recoverable, and SHALL occur once per completed message. A later exact sentinel MAY separate another registered tool name from its arguments, provided the whole call sequence validates before any call is reconstructed.

#### Scenario: Mixed fragments encode two valid calls

- **WHEN** a Mistral response contains text blocks and plain strings that together form a registered tool name, the exact empty sentinel, and two complete valid calls
- **THEN** the runtime emits two native tool calls with the validated arguments, once each
- **AND** it continues the agent loop using their tool results

#### Scenario: Streamed response holds one block per delta

- **WHEN** a streamed Mistral response is aggregated into hundreds of reasoning blocks followed by text blocks forming a registered tool name, the exact empty sentinel, and valid calls
- **THEN** the runtime emits each validated call once, as for the same content in a few blocks

#### Scenario: Streamed response holds empty blocks between deltas

- **WHEN** a streamed Mistral response interleaves blocks without any content (`{}`, or a bare typed marker such as `{"type": "signature"}`) with the text blocks forming a registered tool name, the exact empty sentinel, and valid arguments
- **THEN** the runtime ignores the content-less blocks and emits the validated call once
- **AND** neither assistant nor Planning deltas contain the blocks or encoded call, whether the blocks arrive separately or share a chunk with the sentinel

#### Scenario: Plain answer containing literal braces

- **WHEN** a Mistral answer contains a literal `{}` (for example a code snippet) with no exact sentinel after a registered tool name
- **THEN** the response stays assistant text, unchanged, and no call is reconstructed

#### Scenario: Repeated exact markers encode valid calls

- **WHEN** a Mistral response contains several exact empty sentinels, each immediately following a registered tool name and preceding valid JSON arguments
- **THEN** the runtime emits each validated call once and continues with paired tool results

#### Scenario: Existing native call

- **WHEN** a Mistral response already carries native tool calls and mixed content containing the exact sentinel and valid calls
- **THEN** the runtime emits the text calls first, then the native calls with their IDs
- **AND** a text call equal in name and arguments to a native call is dropped
- **AND** pending encoded call text does not appear in assistant or Planning events

#### Scenario: Sentence ends on the tool name

- **WHEN** the text before an exact sentinel ends with a `.` directly followed by a registered tool name
- **THEN** that tool name anchors the call, and a longer registered dotted name ending the same way wins

#### Scenario: Runaway text after a recovered call

- **WHEN** valid recovered calls are followed or separated by other text
- **THEN** that text is dropped from the message content and only the text before the first call remains

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

The runtime SHALL keep the marker and recoverable call syntax out of assistant answer and reasoning events while the completed Mistral response is being resolved. A recovered call MUST pass the same access, human approval, budget, tracing, observability, and result-pairing controls as a native call. Text before the first recovered call SHALL remain visible through the existing assistant or thought routing; text after it SHALL be dropped, logging only its length. Rendering into assistant text, conversation history, or replayed model context SHALL omit the sentinel and other known non-text call blocks (`reference`, `tool_use`, `tool_call`, `input_json_delta`), SHALL render a `refusal` block as its refusal text, and SHALL omit blocks containing only `type`, `index` and `id` metadata (except malformed `text` or `reference` blocks), and SHALL keep rendering unknown blocks with payloads and non-dict objects visibly.

#### Scenario: Recovered call completes

- **WHEN** a completed mixed-content representation is recovered
- **THEN** the user sees the subsequent answer and normal tool trace, without the marker or encoded call syntax in the answer
- **AND** the call passes the existing gates and has a paired tool result

#### Scenario: Ordinary streamed response

- **WHEN** a Mistral response has ordinary text or an unrecognized typed block and no recoverable complete call
- **THEN** the text remains visible in the assistant answer without being executed

#### Scenario: Unrecovered response keeps the sentinel out of text

- **WHEN** a Mistral response containing the sentinel is not recovered
- **THEN** its text fragments remain visible in order, without a rendering of the sentinel block
- **AND** an unknown typed block in the same response remains visible

### Requirement: Mistral reasoning is replayed natively

When the chat model is a Mistral model served through the OpenAI-compatible client, the runtime SHALL replay each assistant message's reasoning, in every turn of the history, as one native `thinking` chunk followed by its answer text, instead of dropping it or re-homing it as plain text. The size budget SHALL count that reasoning. Every other model SHALL keep the existing handling: reasoning of the open turn re-homed as text, closed-turn reasoning dropped, and no reasoning block in the payload.

#### Scenario: Mistral history carries reasoning

- **WHEN** a Mistral model call replays earlier assistant messages that streamed reasoning
- **THEN** each of those messages reaches the provider with its reasoning as one `thinking` chunk, and its tool calls and IDs unchanged

#### Scenario: Other model history is unchanged

- **WHEN** a non-Mistral model call replays the same history
- **THEN** no `thinking` chunk is sent, and the open turn's reasoning is carried as prefixed text as before

#### Scenario: Recovered response retains reasoning

- **WHEN** a Mistral message contains reasoning and a valid encoded call, optionally duplicating a native call
- **THEN** recovery preserves its reasoning and safe preamble while removing the encoded call
- **AND** the next model request replays that reasoning with paired tool-call and tool-result IDs
