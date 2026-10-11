# Spec Delta

## Purpose

Provide consistent metadata-only logs that let operators follow a Fred operation across APIs, admitted downstream calls, ingestion workers and the frontend pod while preserving diagnostic isolation and existing security boundaries.

## ADDED Requirements

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

Nginx access output SHALL be correctly escaped JSON with event time, HTTP status and severity, without raw query strings or sensitive headers. Native error/startup output SHALL be inventoried and remaining collector parsing limitations SHALL be documented. This behavior SHALL NOT require an extra container or delay API/worker delivery.

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
