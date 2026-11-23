# Spec Delta

## ADDED Requirements

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
