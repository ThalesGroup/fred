# Structured Logging Specification

## Purpose

Provide consistent metadata-only logs that let operators follow a Fred operation across APIs, admitted downstream calls, ingestion workers and the frontend pod while preserving diagnostic isolation and existing security boundaries.

## Requirements

### Requirement: Common application output contract

Fred-controlled Python startup, application, server, warning and permitted exception events SHALL use explicitly selected JSON or readable text output. JSON SHALL be one object per physical stdout line with normalized `severity`, `message`, creation-time `timestamp` containing epoch seconds/nanoseconds, `logger`, stable `service`, applicable service role and source/category information. Embedded newlines SHALL be escaped. Readable output SHALL preserve intentional multiline diagnostics without terminal-width wrapping and SHALL omit ANSI escapes when redirected or colors are disabled. Reinitialization SHALL avoid missing or duplicated events. Existing generic-store representation and optional sink failure/isolation behavior SHALL remain compatible.

#### Scenario: Ordinary event reaches configured output and store

- **WHEN** a standard-library event with scoped context, event properties and embedded newlines is emitted through real JSON setup
- **THEN** stdout contains one valid JSON line with severity, creation timestamp and structured properties, and the optional generic store retains its existing timestamp/level/message representation

#### Scenario: Readable output and repeated initialization

- **WHEN** logging is initialized again and a multiline diagnostic is emitted to redirected readable output
- **THEN** the diagnostic appears once without artificial wrapping or escape codes

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

#### Scenario: Stream fails after transport acceptance

- **WHEN** an SSE request sends HTTP 200 and later fails or disconnects
- **THEN** completion occurs at termination and records the actual transport outcome, while operation diagnostics expose the business failure without implying success from HTTP 200

#### Scenario: A conversation turn resumes

- **WHEN** a new HTTP request resumes an existing business exchange
- **THEN** it has fresh local request identity, retains existing exchange references, and uses existing run/exchange references if no persisted operation correlation is available

#### Scenario: Failed health probe

- **WHEN** a health/readiness request fails
- **THEN** its completion remains visible while successful probes and duplicate access events are suppressed

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

Generic diagnostics SHALL remain metadata-only: no prompts, completions, document contents, tool payloads, credentials, cookies, signed URLs, emails or full user objects. Context validation SHALL reject unsupported values without arbitrary object stringification. Audit events SHALL remain on their dedicated structured channel outside generic stores and SHALL NOT inherit generic context or unrestricted tracebacks. Operational metrics SHALL remain free of user/team/session/request/correlation labels. Bounded sanitized exception diagnostics and existing support references SHALL be retained. Admitted diagnostic IDs, safe route templates and durations SHALL be permitted in generic access logging, superseding the previous neutral-access rule while retaining sensitive-data confinement.

#### Scenario: Generic context and audit output coexist

- **WHEN** scoped generic diagnostics and a security audit event are emitted during the same admitted operation
- **THEN** generic output can carry admitted safe IDs, but audit output obeys its own restrictions and never enters the generic store

#### Scenario: Sensitive request fails before admission

- **WHEN** malformed request bodies, queries or redirects contain credential/content canaries
- **THEN** diagnostics exclude those values at every level, including exception output, while retaining permitted local request references and bounded outcomes

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
