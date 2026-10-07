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
