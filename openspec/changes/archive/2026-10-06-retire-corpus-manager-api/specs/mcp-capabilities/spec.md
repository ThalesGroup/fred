## MODIFIED Requirements

### Requirement: Retired Knowledge Flow MCP servers

Fred's packaged MCP catalog and Knowledge Flow deployment SHALL NOT expose the legacy `mcp-knowledge-flow-corpus` or `mcp-knowledge-flow-fs` servers. Knowledge Flow SHALL NOT expose the legacy corpus-manager HTTP routes under `/corpus/`. Fred SHALL continue to expose supported MCP servers, the independent `/documents/tree` API, and the authenticated HTTP filesystem API used by non-MCP consumers.

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
