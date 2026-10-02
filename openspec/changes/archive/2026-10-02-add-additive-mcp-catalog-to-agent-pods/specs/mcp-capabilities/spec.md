## MODIFIED Requirements

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

## ADDED Requirements

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
