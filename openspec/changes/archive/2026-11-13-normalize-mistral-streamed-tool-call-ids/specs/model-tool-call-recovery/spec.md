## ADDED Requirements

### Requirement: Preserve native streamed tool-call identity across argument fragments

On successful Chat Completions SSE responses, Fred SHALL normalize the string `"null"` to JSON null only on an arguments delta with an absent or empty function name, an integer tool-call index, and an earlier non-empty ID other than `"null"` at the same choice and tool index. Fred SHALL apply this rule by default across Chat Completions routes and honor `settings.normalize_streamed_tool_call_ids: false` for OpenAI-compatible and Azure chat models. Fred SHALL preserve incremental delivery, response diagnostics, timeouts, and upstream closure on normal completion, early close, or cancellation.

#### Scenario: Interleaved argument continuations

- **WHEN** a gateway emits initial tool calls and interleaves argument fragments with quoted null IDs, valid IDs, and omitted IDs
- **THEN** the model assembles each call with its original ID and complete arguments
- **AND** the next request pairs each tool result with the original ID

#### Scenario: Literal ID on a call start

- **WHEN** a tool call starts with the string `"null"` as its ID
- **THEN** that ID and its continuations remain unchanged

#### Scenario: Response is outside normalization scope

- **WHEN** a model disables normalization, a request uses the Responses API, or a response is an HTTP error or a non-SSE body
- **THEN** its body passes through unchanged

#### Scenario: Streams are consumed concurrently

- **WHEN** concurrent streams reuse the same connection pool and a consumer cancels a stream
- **THEN** each stream is normalized using only its own preceding events and the cancelled response releases its connection
