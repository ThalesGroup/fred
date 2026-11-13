# mcp-capabilities Specification

## Purpose
Allow installed packages to supply MCP capabilities and their instructions using
the Fred SDK. Fred's default package owns only platform-provided MCP servers.

## Requirements

### Requirement: SDK-only MCP authoring

MCP capability packages MUST be able to load catalogs and construct capabilities
with the SDK without importing the runtime. Supported server identities,
team policies, composer controls and prompt contents SHALL remain unchanged
except for the explicitly retired legacy document-search, GitHub, corpus and
filesystem servers.

#### Scenario: Standalone package loading
- **WHEN** a package loads its catalog using only SDK dependencies
- **THEN** its supported enabled servers can be constructed as capabilities with their existing metadata

### Requirement: Installed catalog discovery

The pod SHALL discover installed MCP catalogs when no whole-catalog replacement is selected,
use their servers for transport configuration and register each enabled server once.
Duplicate IDs or invalid providers MUST fail startup. With no installed provider
and no additive catalog, the pod SHALL have no MCP servers.
The default `fred-capability-mcp` package SHALL contain only Fred-provided MCPs;
the Fred chart SHALL leave package discovery active by default.

#### Scenario: No MCP sources
- **WHEN** no provider is installed and the additive catalog is absent or empty
- **THEN** the pod registers no MCP server

#### Scenario: Default package without a config directory
- **WHEN** the pod starts with the MCP package installed and no external catalog
- **THEN** the package supplies Fred's internal servers and their complete instruction text
- **AND** no third-party server is included

#### Scenario: Disabled and duplicate servers
- **WHEN** a discovered server is disabled
- **THEN** it is retained in configuration but not registered as a capability
- **WHEN** two installed catalogs declare the same server ID
- **THEN** startup fails rather than selecting one arbitrarily

### Requirement: External catalog compatibility

`FRED_MCP_CATALOG_FILE` SHALL take precedence over an existing
`./config/mcp_catalog.yaml`, which SHALL take precedence over packaged catalogs.
The selected external catalog SHALL replace the entire packaged server set.
Inline `agent_instructions` and `prompt_file` file/resource references MUST remain
supported, and unreadable instruction resources MUST fail startup.

#### Scenario: Empty deployment override
- **WHEN** an explicit external catalog contains no servers
- **THEN** no packaged server is added to transport or capability registration

#### Scenario: Missing selected external file
- **WHEN** an explicitly selected external catalog does not exist
- **THEN** the existing no-MCP startup behavior is retained without falling back to packaged servers

### Requirement: Additive pod MCP catalog

When no whole-catalog replacement is selected, an agent pod SHALL combine
installed MCP catalog providers with an optional deployment-owned
`mcp_catalog_external.yaml`. The default path SHALL be
`./config/mcp_catalog_external.yaml` and
`FRED_MCP_EXTERNAL_CATALOG_FILE` SHALL select another path. Duplicate server
IDs across sources MUST fail startup. The same combined list SHALL feed
transport setup and capability registration.

#### Scenario: Fred pod adds a third-party server
- **WHEN** installed capabilities supply Fred MCPs and the external file defines another server
- **THEN** both sets are available with their original metadata and enabled flags

#### Scenario: Empty or absent default file
- **WHEN** the default external file is absent or contains `servers: []`
- **THEN** installed MCP servers remain available unchanged

#### Scenario: Missing explicit file or duplicate ID
- **WHEN** an explicitly selected external file is missing, or its server ID duplicates an installed one
- **THEN** startup fails before registering MCP capabilities

#### Scenario: Legacy replacement takes precedence
- **WHEN** `FRED_MCP_CATALOG_FILE` selects a whole-catalog replacement
- **THEN** only that replacement is used, regardless of installed providers or the additive file

#### Scenario: Helm values override
- **WHEN** deployment values define a valid external MCP server
- **THEN** the chart renders that server into `mcp_catalog_external.yaml` alongside the model catalog
- **AND** malformed external catalog values are rejected by the chart schema

### Requirement: Internal service references

Internal MCP catalogs SHALL identify a typed Fred service instead of embedding its
URL. The SDK SHALL define the service-address interface, and the runtime SHALL
implement it using existing pod configuration. Resolution MUST preserve the
configured scheme, host, port and API prefix, and append the declared MCP path.
Resolution SHALL happen during catalog loading, without a runtime import in the
capability package. Concrete external URLs SHALL remain supported unchanged.

#### Scenario: Deployment-specific Knowledge Flow address
- **WHEN** the pod configures Knowledge Flow as `https://kf.example:9443/custom/v2/`
  and an internal HTTP MCP names `knowledge_flow` with path `mcp-tabular`
- **THEN** its resolved URL is `https://kf.example:9443/custom/v2/mcp-tabular`
- **AND** transport and capability registration use the same resolved server

#### Scenario: Inprocess Fred service
- **WHEN** an internal MCP identifies Knowledge Flow with the retired `inprocess` transport
- **THEN** catalog validation rejects it; local tools must be supplied as native capabilities

#### Scenario: Invalid service reference
- **WHEN** a catalog names an unknown service, combines a service reference with a
  concrete URL, omits the required HTTP path, or references an unconfigured service
- **THEN** catalog loading fails explicitly without falling back to localhost

#### Scenario: Literal deployment override
- **WHEN** a selected external catalog supplies a concrete MCP URL
- **THEN** loading retains that exact URL regardless of the pod's service addresses

### Requirement: Legacy document-search retirement

The packaged catalog SHALL no longer advertise
`mcp-knowledge-flow-mcp-text`. The runtime SHALL no longer implement its
`kf_vector_search` provider. ReAct RAG, Mindmap and Comparison templates SHALL
retain their identities and default to the native `document_access` capability.
Native document search and other configured MCP servers SHALL remain available.

#### Scenario: Shipped templates after retirement
- **WHEN** the default pod starts after the removal
- **THEN** none of its templates references the retired server
- **AND** the three affected templates declare `document_access` as their default

#### Scenario: Stored explicit capability selections
- **WHEN** the control-plane data migration encounters the retired ID or its
  historic `mcp:`-prefixed form in stored selection/configuration
- **THEN** it removes those entries, preserving unrelated settings and selection order
- **AND** it does not add `document_access` or change permissions, enabled or suspension flags

#### Scenario: Inheritance and repeatability
- **WHEN** the migration encounters missing, null or empty capability selections
- **THEN** it preserves those distinct states while removing any retired config slice
- **AND** a second run makes no further data changes

#### Scenario: Unreadable tuning data
- **WHEN** a stored tuning payload is invalid JSON or is not an object
- **THEN** the migration reports that row without rewriting it or printing its contents

### Requirement: Retired GitHub selections are cleaned from managed agents

The same control-plane data upgrade that retires document-search SHALL remove
`mcp-web-github-readonly` and its historic `mcp:`-prefixed form from stored
agent capability selections and configuration. It MUST preserve unrelated
agent data and SHALL NOT select a replacement capability or change grants and
suspension state.

#### Scenario: Existing agent selects GitHub
- **WHEN** an agent's explicit selection contains either retired GitHub ID
- **THEN** the upgrade removes those selections while preserving other IDs and their order
- **AND** an agent that selected only GitHub has an explicit empty selection

#### Scenario: Inherited defaults and unrelated settings
- **WHEN** a stored selection is absent, null or empty, or a tuning payload contains other configuration
- **THEN** those states and unrelated settings remain intact while retired GitHub config entries are removed
- **AND** reapplying the migration makes no further data changes

#### Scenario: Invalid persisted tuning
- **WHEN** an agent tuning payload is not a JSON object
- **THEN** it is left unchanged with a diagnostic that does not print its contents

### Requirement: MCP uses remote transports only

MCP configuration SHALL accept only `sse`, `stdio`, `websocket` and
`streamable_http` transport identifiers (or the existing null/default value),
and SHALL no longer expose a local `provider` field. The runtime SHALL NOT
instantiate local MCP toolkit factories. Native capability tool execution SHALL
remain available. The unimplemented `mcp-web-github-readonly` catalog entry SHALL
be removed without adding a remote replacement.

#### Scenario: Obsolete local transport
- **WHEN** a deployment loads a catalog declaring `transport: inprocess`
- **THEN** validation fails before tools or capabilities are registered

#### Scenario: Native and remote tools coexist
- **WHEN** an agent selects `document_access` and a supported remote MCP
- **THEN** native search and remote tools keep their existing execution and cleanup paths

### Requirement: Retired Knowledge Flow MCP servers

Fred's packaged MCP catalog and Knowledge Flow deployment SHALL NOT expose the legacy `mcp-knowledge-flow-corpus` or `mcp-knowledge-flow-fs` servers. Knowledge Flow SHALL NOT expose the legacy corpus-manager HTTP routes under `/corpus/`. Fred SHALL continue to expose supported MCP servers, the independent `/documents/tree` API, the read-only virtual corpus view, and authenticated HTTP `/fs` routes retained for technical agent files, including PPT Filler's binary transport.

#### Scenario: Default agent catalog
- **WHEN** an agent pod loads the packaged MCP catalog
- **THEN** neither retired server is selectable or registered, while other packaged servers remain available

#### Scenario: Knowledge Flow MCP routing
- **WHEN** a client requests `/mcp-corpus` or `/mcp-fs`
- **THEN** Knowledge Flow does not provide those MCP transports

#### Scenario: Legacy corpus-management API
- **WHEN** a client requests a former `/corpus/` maintenance route
- **THEN** Knowledge Flow does not expose that route or publish it in OpenAPI

#### Scenario: Non-MCP consumers continue
- **WHEN** an agent lists indexed documents through `document_access` or PPT Filler reads its template and publishes a filled deck through the authenticated HTTP filesystem API
- **THEN** those operations continue to work without either retired MCP server or the corpus-manager facade

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

### Requirement: Tabular query details remain responsive for large returned payloads

Opening a supported tabular query step SHALL expose its recorded SQL and query status without first rendering or syntax-highlighting the full returned dataset. The initial response preview SHALL bound visible rows, columns and cell text and SHALL identify omitted data in one compact localized sentence, including complete-copy behavior when available. The bounded JSON preview SHALL retain the existing syntax colors and code-block presentation. Tool details MUST NOT invent token counts from payload character lengths. The original SQL and complete recorded response SHALL remain copyable without changing their contents. Oversized SQL SHALL receive a bounded visible preview with an explicit truncation indication and access to its complete original through copying. Live and reloaded traces SHALL use the same interpretation; opening a step SHALL NOT re-run its tool.

#### Scenario: Wide query response
- **GIVEN** a successful query result with hundreds of rows and dozens of columns
- **WHEN** the user opens its trace step
- **THEN** the drawer displays SQL above a bounded response preview and identifies the returned row count and preview limits
- **AND** initial rendered work does not grow with the total number of returned cells

#### Scenario: Oversized cell or SQL
- **WHEN** a query contains very long SQL or its result contains a very long cell
- **THEN** the visible preview is bounded and identifies truncation
- **AND** copying the SQL or recorded response preserves the complete original content

#### Scenario: Reopen, switch or stream
- **WHEN** a user opens a recorded query, switches to another step, reopens the query or receives unrelated streaming text
- **THEN** the drawer remains responsive and shows the selected call's SQL and preview without executing another query

#### Scenario: Failure and unknown-tool compatibility
- **WHEN** a failed supported tabular call or an unsupported tool is inspected
- **THEN** existing safe failure diagnostics and unknown-tool redaction remain in force

### Requirement: Tabular details do not attribute full model usage to an individual tool

The tabular tool drawer MUST NOT label a model request's complete prompt or completion counters as tokens sent or received by an individual tool. This applies to requesting, following and historical model-response metadata, including shared tool batches. When the tool API supplies no token breakdown for that tool, the drawer SHALL omit token counters rather than substitute global model usage, derive an estimate or claim zero consumption. The drawer SHALL retain status, duration, SQL, bounded syntax-colored results and complete supported-copy behavior, without an added model-usage explanation paragraph.

#### Scenario: One returned row and large model context
- **GIVEN** a tabular query returns one row without tool-specific API usage
- **AND** the following model response reports 59260 input and 12426 output tokens
- **WHEN** the user opens the tool details
- **THEN** no tool token badges display those global model counters
- **AND** the status, duration, SQL and returned row remain available without a model-usage explanation paragraph

#### Scenario: Live updates and reload
- **WHEN** model-call usage arrives after a tool result or the conversation is reloaded with model usage metadata
- **THEN** the tool drawer does not reinterpret that metadata as an individual tool's consumption

#### Scenario: Missing or zero model usage
- **WHEN** model metadata has missing, invalid or zero counters but no tool-specific API breakdown exists
- **THEN** no estimated, unavailable-placeholder or zero-valued tool consumption badge is displayed

#### Scenario: Shared model response
- **WHEN** one model exchange includes results from several tools
- **THEN** its full request and response usage is not presented as the consumption of each tool
- **AND** existing conversation accounting remains unchanged
