## ADDED Requirements

### Requirement: Caught MCP failures provide bounded non-empty feedback

The runtime SHALL provide non-empty Fred-owned feedback for every caught MCP failure. Recognized failures SHALL explain a safe cause and appropriate next action. Unknown failures SHALL use a fixed generic message. Only the existing curated `read_query` HTTP 400 diagnostic SHALL expose dynamic SQL error detail. Provider response bodies, exception representations, credentials and private URLs MUST NOT become generic user-facing error text. Delegated authority refusals and cancellation SHALL retain their existing stopping behavior.

#### Scenario: Authentication failure before a tabular invocation
- **WHEN** an attachment-inventory request fails with an expired-token HTTP 401 during preparation of a tabular call
- **THEN** the caught failure contains a non-empty authentication explanation and reconnection guidance without exposing the credential or request URL
- **AND** it does not report an invalid SQL expression or a completed query

#### Scenario: Known failure or unknown exception
- **WHEN** a caught MCP error has a recognized unavailable-resource, invalid-argument, overload or timeout category
- **THEN** its result contains a bounded explanation appropriate to that category
- **WHEN** no safe category is available or the error artifact has no usable blocks
- **THEN** the result contains the fixed generic failure message instead of an empty diagnostic

#### Scenario: Curated SQL detail and authority loss
- **WHEN** `read_query` returns its supported HTTP 400 SQL diagnostic
- **THEN** the model and user-facing result retain the existing redacted diagnostic
- **WHEN** delegated authority is lost or the operation is cancelled
- **THEN** the existing stopping behavior is preserved rather than converted into a retryable tool result

### Requirement: Failed tool details explain the action and recorded safe cause

The existing chat trace drawer SHALL show the failed action, a non-empty safe explanation, available recovery guidance and duration. For supported tabular failures it SHALL show an authorized document name when already available and the submitted SQL for `read_query`. It SHALL use the same interpretation for live and reloaded history, support French and English labels, and retain failure status without claiming zero returned rows. Generic failures SHALL NOT reveal arbitrary tool arguments or provider-controlled text.

#### Scenario: Supported failure in live or reloaded history
- **WHEN** a user opens a failed tabular tool step with a recognized Fred-owned diagnostic
- **THEN** the drawer explains the action and recorded cause with its recovery guidance
- **AND** reopening the conversation presents the same diagnostic and failure status

#### Scenario: Authorized document context
- **WHEN** an earlier authorized discovery result identifies the requested document within the exchange
- **THEN** the failure detail can show that document's human-readable name
- **AND** opaque document UIDs, SQL aliases and unrelated tool arguments are not printed as context

#### Scenario: Empty historical or untrusted diagnostic
- **WHEN** a failed result has an empty diagnostic, unrecognized provider text or a malformed diagnostic message
- **THEN** the drawer shows a localized fallback indicating that no further safe diagnostic was recorded
- **AND** no arbitrary response text, credential or private URL is revealed
