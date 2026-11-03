## MODIFIED Requirements

### Requirement: The request API describes the buffered protocol accurately

The public request API SHALL accept the protocol's string-or-null body and, when the connected
host announces binary bodies, a `Blob` or `FormData` body; it SHALL reconstruct a browser
`Response` from a successful `fred:response` whose body is buffered text or a `Blob`. A binary
body sent to a host that does not announce the capability MUST reject locally without posting.
HTTP error statuses including 401, 403, and 5xx MUST resolve as Responses whose status and
headers remain inspectable; `fred:response-error` and local transport failures MUST reject
separately. HEAD and status 204, 205, or 304 responses MUST be reconstructed without a body so
bodyless replies do not throw during construction.

Documentation MUST identify this as a buffered transport rather than full Fetch equivalence,
state that binary bodies need a host announcing them, and state that upload size is bounded by
the host gateway. It MUST NOT promise response streaming, transfer progress, SSE, remote
cancellation, detailed host transport reasons, or automatic retry.

#### Scenario: A successful JSON response arrives

- **WHEN** the host returns a successful status, headers, and a buffered JSON body as text or as a `Blob`
- **THEN** the resolved Response exposes the same status and headers and its text or JSON
  reader consumes the buffered body

#### Scenario: A binary body is sent to a host without the capability

- **WHEN** a consumer sends a `Blob` or `FormData` body before a host announcing binary bodies has connected it
- **THEN** the request rejects locally with an unsupported-by-host error and no message is posted

#### Scenario: The application service returns an HTTP error

- **WHEN** the host returns 401, 403, or a 5xx `fred:response`
- **THEN** the request resolves with that non-OK Response rather than becoming an SDK
  transport exception

#### Scenario: The host reports a transport failure

- **WHEN** the host sends `fred:response-error` for a pending request
- **THEN** the request rejects with a generic transport error that does not invent or
  expose a host-side reason

#### Scenario: A bodyless response arrives

- **WHEN** a HEAD request or 204, 205, or 304 response carries the host's buffered empty
  string or an empty `Blob`
- **THEN** the SDK constructs a valid bodyless Response while preserving status and
  headers
