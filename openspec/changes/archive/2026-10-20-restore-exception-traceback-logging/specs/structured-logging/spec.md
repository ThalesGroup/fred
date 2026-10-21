## MODIFIED Requirements

### Requirement: Common application output contract

Fred-controlled Python startup, application, server, warning and permitted exception events SHALL use explicitly selected JSON or readable text output. JSON SHALL be one object per physical stdout line with normalized `severity`, `message`, creation-time `timestamp` containing epoch seconds/nanoseconds, `logger`, stable `service`, applicable service role and source/category information. Embedded newlines SHALL be escaped. Readable output SHALL preserve intentional multiline diagnostics without terminal-width wrapping and SHALL omit ANSI escapes when redirected or colors are disabled. Reinitialization SHALL avoid missing or duplicated events. Existing generic-store representation and optional sink failure/isolation behavior SHALL remain compatible.

Application and server events carrying exception information SHALL preserve the exception type, ordinary exception message, traceback frames and standard visible exception chains in stdout output, subject to targeted redaction of known credential-bearing URL patterns. Enabling either delegation direction SHALL NOT suppress this information or replace server error messages with a fixed diagnostic. Traceback rendering SHALL NOT add local variable values.

#### Scenario: Ordinary event reaches configured output and store

- **WHEN** a standard-library event with scoped context, event properties and embedded newlines is emitted through real JSON setup
- **THEN** stdout contains one valid JSON line with severity, creation timestamp and structured properties, and the optional generic store retains its existing timestamp/level/message representation

#### Scenario: Readable output and repeated initialization

- **WHEN** logging is initialized again and a multiline diagnostic is emitted to redirected readable output
- **THEN** the diagnostic appears once without artificial wrapping or escape codes

#### Scenario: Exception output is independent of delegation

- **WHEN** an application or server event carries an exception with an ordinary diagnostic message and visible cause, with both delegation switches off or either switch on
- **THEN** JSON output contains the message, exception type and traceback with its visible cause in one valid physical line, and readable output retains the corresponding multiline diagnostic

### Requirement: Request and operation lifecycle diagnostics

Each inbound request SHALL receive a fresh local request ID, regardless of supplied metadata, and a root correlation ID unless admitted propagation supplies one. Responses SHALL expose local request and operation references through headers and applicable CORS exposure. HTTP logging SHALL emit one completion event at actual request/stream termination, carrying method, safe route template when available, actual sent status when available, outcome, numeric duration and current permitted context. Unmatched routes SHALL NOT substitute raw URLs. Successful health/readiness probes SHALL be suppressed; failures SHALL remain visible. Conversation creation, turns/resumes, agent/tool execution, uploads and attachments SHALL bind available owned references and emit business outcomes independently of transport acceptance.

For an uncaught request exception that has not already been logged by application code and produces HTTP 500, the standard response/error path SHALL produce one ERROR exception diagnostic and one separate ERROR HTTP completion event. Both events SHALL retain the same available admitted user, session, agent, team, request and correlation references from the request-owned diagnostic snapshot, including when inner scopes have retired or work crossed a middleware task boundary. The exception diagnostic SHALL remain discoverable with the same identity filters as completion; a later context-free server report SHALL NOT be its sole diagnostic. Missing or unadmitted references SHALL NOT be invented. Concurrent and later requests SHALL NOT inherit another request's identity.

The completion event SHALL NOT repeat the traceback. Once the request boundary reports an exception, its duplicate server exception event SHALL be suppressed without suppressing distinct, unreported or non-request server failures. A handled HTTP 500 or explicit 500 response without attached exception information SHALL NOT cause the infrastructure to fabricate an exception diagnostic. Completion events and response reference headers SHALL retain their existing identity behavior.

#### Scenario: Stream fails after transport acceptance

- **WHEN** an SSE request sends HTTP 200 and later fails or disconnects
- **THEN** completion occurs at termination and records the actual transport outcome, while operation diagnostics expose the business failure without implying success from HTTP 200

#### Scenario: A conversation turn resumes

- **WHEN** a new HTTP request resumes an existing business exchange
- **THEN** it has fresh local request identity, retains existing exchange references, and uses existing run/exchange references if no persisted operation correlation is available

#### Scenario: Failed health probe

- **WHEN** a health/readiness request fails
- **THEN** its completion remains visible while successful probes and duplicate access events are suppressed

#### Scenario: An uncaught request failure reaches the server

- **WHEN** an otherwise unlogged exception escapes a controller and the ordinary server-error handler produces HTTP 500
- **THEN** there is one exception ERROR with traceback and one completion ERROR with status, route, duration and outcome, sharing the available request-owned references, without an additional detail-free error or duplicate server exception report

#### Scenario: An exception follows business identity across a middleware task boundary

- **WHEN** admitted user, session, agent and team references are resolved inside a middleware child task that raises an uncaught exception
- **THEN** both the exception diagnostic and completion event contain those same references and the response's request/correlation IDs even if the emitting parent task's ambient context lacks the business references

#### Scenario: Concurrent failing requests remain independently searchable

- **WHEN** two requests with different admitted user, session, agent, team and correlation references fail concurrently, followed by another request
- **THEN** filtering by either failing request's available identity finds its exception and completion events, excludes the other request's events, and the later request inherits neither identity

#### Scenario: An unrelated server error remains visible

- **WHEN** a distinct server failure has not been reported by the request boundary, even if its message matches a previously reported failure
- **THEN** its exception diagnostic remains visible and duplicate suppression does not discard it

#### Scenario: A controller converts a logged failure into an HTTP response

- **WHEN** a controller logs its exception once and converts it into a handled HTTP 500
- **THEN** its exception diagnostic retains the traceback and the HTTP logger emits the separate completion ERROR without an additional server exception diagnostic

#### Scenario: An explicit HTTP 500 has no attached exception information

- **WHEN** a controller returns HTTP 500 or raises a handled HTTP 500 without logging an underlying exception
- **THEN** the completion ERROR remains visible and the infrastructure does not invent a traceback

### Requirement: Existing diagnostic safeguards remain enforced

Ordinary generic messages and structured context SHALL remain metadata-only: no prompts, completions, document contents, tool payloads, credentials, cookies, signed URLs, emails or full user objects SHALL be deliberately added to those fields. Exception diagnostics SHALL instead follow the common application output contract: their ordinary messages and traceback frames SHALL be retained with targeted redaction, rather than removed through blanket diagnostic suppression. Known `token`, `access_token` and `id_token` URL query values, and invitation secrets in the existing free-access and join-link paths, SHALL be redacted from server messages, string arguments and rendered exception diagnostics, including visible exception chains. This targeted policy SHALL NOT claim to detect arbitrary sensitive values embedded in free-form exception text.

Context validation SHALL reject unsupported values without arbitrary object stringification. Audit events SHALL remain on their dedicated structured channel outside generic stores and SHALL NOT inherit generic context or unrestricted tracebacks. Operational metrics SHALL remain free of user/team/session/request/correlation labels. Existing bounded runtime support references and dependency diagnostic restrictions SHALL remain unchanged. Admitted diagnostic IDs, safe route templates and durations SHALL remain permitted in generic access logging; raw request bodies, headers and local variables SHALL NOT be added automatically to exception output.

#### Scenario: Generic context and audit output coexist

- **WHEN** scoped generic diagnostics and a security audit event are emitted during the same admitted operation
- **THEN** generic output can carry admitted safe IDs, but audit output obeys its own restrictions and never enters the generic store

#### Scenario: Sensitive request fails before admission

- **WHEN** malformed request bodies, queries or redirects contain credential/content canaries and the request fails before admission
- **THEN** completion events, structured context and audit output retain their existing confinement, while exception diagnostics follow the targeted-redaction contract without automatically adding raw request bodies, headers or full user objects

#### Scenario: A known URL credential appears only in an exception cause

- **WHEN** an exception or visible cause embeds a recognized token-bearing query or invitation URL while the server log message contains no such URL
- **THEN** the credential value is redacted from JSON and readable exception output while the useful diagnostic text, exception type and traceback remain visible

#### Scenario: An ordinary exception message is preserved

- **WHEN** an exception includes ordinary diagnostic text outside the known redaction patterns
- **THEN** that text remains available with its traceback regardless of delegation, without a fixed-message substitution
