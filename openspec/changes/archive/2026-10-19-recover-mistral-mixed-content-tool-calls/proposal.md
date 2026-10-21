## Why

A live Deep turn using Mistral Medium 3.5 ended with two intended `read_query` invocations printed as its final answer. A second supplied exchange shows the same fragment shape for `search_documents_using_vectorization`. The provider response stored for that turn contains text dictionaries, plain string fragments, and an empty `reference` block in one content list. The first recovery and streaming paths recognized only all-dictionary content, so the tools never ran and the marker reached the user. Follow-up sessions show two remaining shapes: a native tool call with the same marker and call syntax in assistant content, and a completed response with a second exact marker between valid calls. This is a captured failure for [#2746](https://github.com/ThalesGroup/fred/issues/2746).

## What Changes

- Extend completed-message Mistral tool-call recovery to handle a bounded mixed content list of text blocks and plain string fragments around the existing exact empty `reference` sentinel.
- Keep recovery gated by Mistral identity, a registered tool name, strict complete JSON arguments, and the tool's input schema. Preserve native calls and reject ambiguous or malformed content.
- Make the streamed-output bridge recognize the same mixed shape, withholding recoverable call syntax and the sentinel until the completed-message decision, while releasing ordinary text.
- Accept repeated exact markers only when each one follows a registered tool name and all calls validate together. When a response already has native calls, withhold pending marked syntax from its streamed answer and Planning preamble while preserving those calls.
- Add redacted regression fixtures based on the captured checkpoints, with ReAct and Deep checks for execution, UI output, and existing tool gates.
- Follow-up [#3110](https://github.com/ThalesGroup/fred/issues/3110): a streamed reasoning response holds one content block per delta, so the 256-block cap rejected every long Mistral turn before parsing. Bound recovery by text size and call count only, omit payloadless provider blocks consistently in parsing and streaming, stop rendering the sentinel and tool-call blocks as their Python repr (unknown blocks with payloads stay visible, refusals render as text), and drop runaway text after recovered calls while retaining reasoning for replay.
- Leak-study follow-up (2026-10-19): replay Mistral's reasoning in the history as native `thinking` chunks, as Mistral's docs ask, instead of dropping it. In a live A/B on `mistral-medium` with `reasoning_effort: high` (12 runs per arm) it took text-written tool calls from 26/146 calls to 0/188, delivered decks from 7/12 to 12/12, and runaway hangs from 3 to 0.

## Capabilities

### New Capabilities

- `model-tool-call-recovery`: Defines when a provider response that encodes an intended tool call in assistant content becomes a native call and how its streamed representation is handled.

### Modified Capabilities

None.

## Impact

- Runtime Mistral recovery middleware, shared content decoding, ReAct and Deep streaming, and targeted runtime tests.
- No API, database, or frontend contract change is planned. The visible effect is that this validated representation follows the normal tool path instead of appearing as a final answer.
