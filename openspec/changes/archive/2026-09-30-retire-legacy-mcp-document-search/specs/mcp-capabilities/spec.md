## MODIFIED Requirements

### Requirement: SDK-only MCP authoring

MCP capability packages MUST be able to load catalogs and construct capabilities
with the SDK without importing the runtime. Supported server identities,
team policies, composer controls and prompt contents SHALL remain unchanged
except for the explicitly retired legacy document-search and GitHub servers.

#### Scenario: Standalone package loading
- **WHEN** a package loads its catalog using only SDK dependencies
- **THEN** its supported enabled servers can be constructed as capabilities with their existing metadata

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

## ADDED Requirements

### Requirement: Legacy document-search retirement

The packaged and Helm catalogs SHALL no longer advertise
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
