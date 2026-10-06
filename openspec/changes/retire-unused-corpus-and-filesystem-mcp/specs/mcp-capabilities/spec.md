## ADDED Requirements

### Requirement: Retired Knowledge Flow MCP servers
Fred's packaged MCP catalog and Knowledge Flow deployment SHALL NOT expose the legacy `mcp-knowledge-flow-corpus` or `mcp-knowledge-flow-fs` servers. Fred SHALL continue to expose supported MCP servers and SHALL preserve the underlying HTTP corpus-management and filesystem APIs used by non-MCP consumers.

#### Scenario: Default agent catalog
- **WHEN** an agent pod loads the packaged MCP catalog
- **THEN** neither retired server is selectable or registered, while other packaged servers remain available

#### Scenario: Knowledge Flow MCP routing
- **WHEN** a client requests `/mcp-corpus` or `/mcp-fs`
- **THEN** Knowledge Flow does not provide those MCP transports

#### Scenario: Non-MCP consumers continue
- **WHEN** PPT Filler reads its template or publishes a filled deck through the authenticated HTTP filesystem API
- **THEN** those operations continue to work without either retired MCP server
