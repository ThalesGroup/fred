## ADDED Requirements

### Requirement: MCP v2 interoperability

Fred SHALL discover and call tools on MCP v2-compatible remote servers through its implemented HTTP and stdio transports. Knowledge Flow SHALL expose its enabled MCP tool servers to MCP v2-compatible clients at their existing paths without requiring clients to remain on the MCP v1 Python SDK.

#### Scenario: Agent calls a remote v2 tool
- **WHEN** an agent loads an enabled `streamable_http` or `stdio` MCP server compatible with MCP v2 and calls one of its tools
- **THEN** Fred lists and invokes that tool and returns its result through the existing agent tool path

#### Scenario: Knowledge Flow serves a v2 client
- **WHEN** an authorized MCP v2 client lists and invokes an enabled Knowledge Flow tool server
- **THEN** it sees the same selected tools, names, input schemas, and curated results at the existing mount path

### Requirement: MCP v2 authorization continuity

MCP v2 tool discovery and invocation MUST preserve Fred's current person-token and delegated-authority boundaries. Credential refresh and authority refusal SHALL be evaluated for each tool call, and sensitive credentials and grants MUST NOT enter tool arguments, model transcripts, or logs.

#### Scenario: Person token changes after discovery
- **WHEN** an agent's own-identity token changes between listing and invoking a remote MCP tool
- **THEN** the invocation uses the current token and an expired token triggers at most one refresh retry

#### Scenario: Delegated authority ends
- **WHEN** a delegated run ends or its Knowledge Flow receiver refuses the grant
- **THEN** Fred stops the tool call with its existing authority-loss behavior and does not retry under a different identity

#### Scenario: Multi-pod Knowledge Flow
- **WHEN** consecutive MCP v2 requests for one Knowledge Flow tool are routed to different service pods
- **THEN** the call succeeds without a pod-local session requirement, subject to the same authorization checks
