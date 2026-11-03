# Structured Logging Specification

## Purpose

Provide consistent application and exception diagnostics that let operators follow a Fred operation across APIs, admitted downstream calls, ingestion workers and the frontend pod while preserving scoped identity, audit isolation and the documented credential-redaction policy.

## Requirements

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

### Requirement: Scoped context remains isolated and authoritative

Logs SHALL acquire safe diagnostic identity only from authenticated/admitted principals and the orchestration that owns resolved business references. Session, exchange, template, instance and run references SHALL retain distinct meanings. Nested scopes SHALL restore outer values on success, error and cancellation, including explicit clearing; concurrent requests/jobs SHALL remain isolated. Context SHALL be captured in the producing task before asynchronous logging delivery. Event properties SHALL NOT override core event metadata or currently bound identity fields. Logging context SHALL NOT authorize any operation.

#### Scenario: Interleaved requests and a subsequent request

- **WHEN** two differently authenticated requests interleave nested work and one fails or is cancelled, followed by a third request
- **THEN** each emitted event retains its own context and the third request inherits no stale identifiers

#### Scenario: Event properties collide with owned identity

- **WHEN** event properties contain a core field or an identity already bound by trusted orchestration
- **THEN** the owned value wins and unrelated safe event properties remain queryable

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

### Requirement: Propagation requires delegated admission

Safe bound logging context SHALL cross first-party REST/MCP calls only through active delegated credential paths and SHALL be accepted only after existing delegated principal/grant admission succeeds. The transport SHALL use one documented versioned bounded encoding with JSON-safe value and reserved-name validation. All safe bound fields except reserved fields SHALL propagate without a second business-field allowlist; one-off event properties, auth objects and arbitrary runtime context SHALL NOT propagate. Headers SHALL be attached per invocation without mutating shared-client defaults or reaching unrelated providers, authentication endpoints or redirected untrusted destinations. Receiver-owned event/request/service/role/host/process/task/source/category/tracing fields SHALL win. Principal and grant-covered identities SHALL come from admission; inherited business context SHALL remain until locally resolved or explicitly cleared.

#### Scenario: Admitted first-party call

- **WHEN** a valid delegated call carries safe correlation/team/resource context alongside spoofed receiver-owned and principal fields
- **THEN** safe inherited fields survive, a new local request ID is created, and local event identity plus admitted principal/grant identities win

#### Scenario: Untrusted or malformed metadata

- **WHEN** delegation is disabled, the caller uses an ordinary user bearer, or metadata is malformed, unsupported or oversized
- **THEN** propagation is ignored, local context remains valid, and otherwise valid business requests are not rejected because of logging metadata

#### Scenario: Authentication fails

- **WHEN** delegated authentication or grant admission fails despite supplied logging metadata
- **THEN** the original authentication failure remains authoritative and unadmitted identity fields do not enter diagnostics

### Requirement: Trusted jobs retain context across ingestion and retries

Existing trusted scheduling/admission SHALL persist an optional bounded safe logging envelope without credentials and without weakening scheduler authorization. Worker output SHALL use the common format and bind existing job/document/workflow/run/activity IDs and attempt number. Retries SHALL preserve operation/business references while exposing changed attempt identity. Work without originating request context SHALL obtain local correlation outside deterministic workflow code. Old jobs without envelopes SHALL remain executable. Workflow logging SHALL respect replay and sandbox constraints and SHALL NOT perform direct network export or nondeterministic context generation.

#### Scenario: Durable ingestion retry

- **WHEN** an admitted upload is persisted, delivered later and retried in a worker activity
- **THEN** logs retain its safe operation/document references and expose the current local activity attempt

#### Scenario: Legacy scheduled payload

- **WHEN** a worker receives an existing queued job without a logging envelope
- **THEN** the job executes with local identifiers and no requirement for an HTTP delegation check

### Requirement: Frontend pod access logs remain parseable

Nginx access output SHALL be correctly escaped JSON with event time, HTTP status and severity, without raw query strings or sensitive headers. Native error/startup output SHALL be inventoried and remaining collector parsing and request-detail exposure limitations SHALL be documented. Native text SHALL NOT be represented as sanitized JSON access output. This behavior SHALL NOT require an extra container or delay API/worker delivery.

#### Scenario: Access request contains sensitive query data

- **WHEN** nginx serves a request containing query credentials and characters requiring JSON escaping
- **THEN** access output remains valid JSON and query credentials are absent

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

### Requirement: First party MCP failures retain inner HTTP diagnostics

For each completed first-party MCP inner HTTP operation with status >= 400, the system SHALL emit exactly one structured `mcp.inner_http_failure` diagnostic before returning or converting that failure. It SHALL identify the registered tool, safe route template and method when available, the actual inner HTTP status, and valid receiver-owned request/correlation references from the response as separate upstream references. Missing route metadata or invalid/missing response references SHALL remain absent without changing the tool result. Client failures SHALL use warning severity and server failures SHALL use error severity. Diagnostic body inspection SHALL leave the response readable by normal MCP processing.

#### Scenario: Inner 404 inside successful MCP transport

- **WHEN** a description operation returns inner HTTP 404 while its outer MCP request completes with HTTP 200
- **THEN** a bridge warning identifies the registered description tool, inner route and 404, links to the inner receiver request when available, and retains the outer request's own identity without interpreting HTTP 200 as tool success

#### Scenario: Authority refusal and curated SQL failure

- **WHEN** an inner operation produces an authority refusal or a curated SQL HTTP 400 result
- **THEN** the diagnostic retains the actual inner status before the authority-stop result or standard MCP error carrying the curated SQL detail is produced

#### Scenario: Response remains readable after diagnostics

- **WHEN** diagnostics inspect a completed inner failure before MCP error conversion
- **THEN** normal processing can still read its body and return the standard failed tool result with its HTTP status and response detail, while the logs retain only permitted metadata

#### Scenario: No completed HTTP response

- **WHEN** the inner operation raises a transport exception or is cancelled before a response is available
- **THEN** diagnostics do not invent an HTTP status or replace the original exception or cancellation

#### Scenario: No valid receiver reference

- **WHEN** a response reference is missing, malformed or exceeds the accepted bound
- **THEN** the diagnostic omits it, retains known status/tool facts and does not substitute caller-supplied references

### Requirement: Tabular discovery and description explain resolution outcomes

Tabular discovery that completes with no documents SHALL emit one informational resolution summary derived from work already performed. The summary SHALL distinguish no readable documents, an empty authorized scope, no document matching the scope and no registered tables through closed reason codes and nonnegative stage counts. Expected description failures SHALL emit a warning with a closed reason distinguishing unresolved datasets, an incomplete preview and an unavailable preview artifact. Diagnostics SHALL use existing local authenticated/resolved context and SHALL NOT introduce extra authorization checks, metadata fetches or artifact reads solely for logging.

#### Scenario: Metadata exists but active scope excludes it

- **WHEN** authorized metadata is resolved but none of those documents match the requested authorized scope
- **THEN** the empty-discovery summary identifies scope exclusion with stage counts, without claiming the documents are unregistered or changing the successful empty response

#### Scenario: Scoped documents have no queryable tables

- **WHEN** scoped readable documents resolve but none have usable registered table descriptors
- **THEN** the empty-discovery summary identifies absence of registered tables using a reason distinct from scope exclusion

#### Scenario: Description cannot resolve an allowed dataset

- **WHEN** a requested dataset remains unresolved and the existing individual permission check permits its requested document
- **THEN** the description warning identifies dataset resolution failure under the receiver request identity, and the existing HTTP status and response detail remain unchanged

#### Scenario: Preview readiness differs from preview availability

- **WHEN** a description fails because the preview stage is incomplete or because the preview artifact cannot be obtained
- **THEN** the warning uses the corresponding distinct reason without including the artifact path, contents or storage exception text

### Requirement: Failure diagnostics preserve isolation and existing error boundaries

The added diagnostics SHALL contain only closed classifications, known registered operation metadata, bounded counts, locally admitted/resolved context and validated receiver references. They SHALL NOT include raw HTTP details/bodies, queries, tool arguments, SQL, arbitrary header contents, exception strings, credentials, signed URLs or document contents. Dependency logs emitted during MCP execution SHALL retain existing diagnostic confinement, including body-bearing exceptions and concrete request paths. Concurrent calls SHALL keep their references isolated. Diagnostic classification SHALL NOT change authorization, retries, HTTP route responses, curated SQL detail or agent-side error presentation. Emission SHALL NOT depend on traceback formatting, expand existing context admission, or add identity dimensions to operational metrics.

#### Scenario: Sensitive upstream body and arguments

- **WHEN** a failed first-party tool invocation includes secret and content canaries in its response body, arguments, query or arbitrary response headers
- **THEN** explicit failure events and dependency diagnostics in every configured logging sink exclude those canaries while preserving permitted status, registered operation and receiver-reference facts; this restriction does not require replacing ordinary MCP error text with a blanket message

#### Scenario: Concurrent admitted calls

- **WHEN** two differently scoped admitted tool operations interleave and one fails
- **THEN** each diagnostic retains only its own request context and inner references, each route receives only its verified delegation values, and the failed operation follows its applicable MCP error contract

#### Scenario: Reserved delegation values are model controlled

- **WHEN** a tool invocation supplies forged reserved grant fields in query parameters or a top-level JSON body
- **THEN** the inner route receives only the mount-verified grant for delegation, unrelated payload fields remain intact, and supplied logging context cannot override trusted context

#### Scenario: Authority is refused inside a tool operation

- **WHEN** the inner route returns HTTP 401/403 or the existing account-status-unavailable HTTP 503 marker
- **THEN** the failure diagnostic is emitted and the MCP result retains `isError=true` with `structuredContent={"cause": "authority_lost"}` so the runtime stops the run; an unmarked HTTP 503 remains an ordinary failed tool result

#### Scenario: Inner response redirects

- **WHEN** an inner route returns a redirect
- **THEN** the MCP inner client does not follow it or forward the verified grant and trusted context to its target
