## ADDED Requirements

### Requirement: Caught MCP failures provide bounded non-empty feedback

The runtime SHALL provide non-empty Fred-owned feedback for every caught MCP failure. Recognized failures SHALL explain a safe cause and appropriate next action to the model. Unknown failures SHALL use a fixed generic message. Only the existing curated `read_query` HTTP 400 diagnostic SHALL expose dynamic SQL error detail. Provider response bodies, exception representations, credentials and private URLs MUST NOT become generic user-facing error text. Delegated authority refusals and cancellation SHALL retain their existing stopping behavior.

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

The existing chat trace drawer SHALL show the failed action, its recorded business arguments and the error preserved by the trusted boundary. It SHALL remain an explanatory view without a next-step section or recovery advice. For supported tabular failures it SHALL preserve the submitted document selectors, SQL, keyword and result-limit arguments where applicable, including invalid values that explain the failed invocation. It SHALL use the same interpretation for live and reloaded history, support French and English labels, and retain failure status without claiming zero returned rows. Argument display MUST exclude credentials, injected authentication/scope internals and unsupported arbitrary provider fields.

#### Scenario: Supported failure in live or reloaded history
- **WHEN** a user opens a failed tabular tool step with a recognized Fred-owned diagnostic
- **THEN** the drawer displays the action, recorded business arguments and safe recorded error without a next-step section or recovery advice
- **AND** reopening the conversation presents the same diagnostic and failure status

#### Scenario: Failed invocation arguments remain inspectable
- **WHEN** a tabular call fails after submitting a document selector, SQL expression, keyword or result limit
- **THEN** the drawer displays those recorded business arguments without replacing incorrect values with inferred corrections
- **AND** an available authorized document name can supplement the argument block without hiding the identifier actually submitted

#### Scenario: Agent recovery guidance stays outside the explanatory view
- **WHEN** a recognized error includes recovery guidance for the agent
- **THEN** the drawer displays its diagnostic portion without a separate next-step section or generated recovery advice
- **AND** the submitted arguments and safe error remain available

#### Scenario: Empty historical or untrusted diagnostic
- **WHEN** a failed result has an empty diagnostic, unrecognized provider text or a malformed diagnostic message
- **THEN** the drawer shows a localized fallback indicating that no further safe diagnostic was recorded
- **AND** no arbitrary response text, credential or private URL is revealed
