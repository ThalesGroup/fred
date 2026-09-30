## Purpose

Allow installed packages to supply MCP capabilities and their instructions using
the Fred SDK, while retaining deployment-owned server configuration.

## ADDED Requirements

### Requirement: SDK-only MCP authoring

MCP capability packages MUST be able to load catalogs and construct capabilities
with the SDK without importing the runtime. Existing server identities,
team policies, composer controls and prompt contents SHALL remain unchanged.

#### Scenario: Standalone package loading
- **WHEN** a package loads its catalog using only SDK dependencies
- **THEN** its enabled servers can be constructed as capabilities with their existing metadata

### Requirement: Installed catalog discovery

The pod SHALL discover installed MCP catalogs when no external catalog is selected,
use their servers for transport configuration and register each enabled server once.
Duplicate IDs or invalid providers MUST fail startup. No installed provider SHALL
result in no external MCP servers.

#### Scenario: Default package without a config directory
- **WHEN** the pod starts with the MCP package installed and no external catalog
- **THEN** the package supplies the existing servers and their complete instruction text

#### Scenario: Disabled and duplicate servers
- **WHEN** a discovered server is disabled
- **THEN** it is retained in configuration but not registered as a capability
- **WHEN** two installed catalogs declare the same server ID
- **THEN** startup fails rather than selecting one arbitrarily

### Requirement: External catalog compatibility

`FRED_MCP_CATALOG_FILE` SHALL take precedence over an existing
`./config/mcp_catalog.yaml`, which SHALL take precedence over packaged catalogs.
The selected external catalog SHALL replace the entire packaged server set.
Inline instructions and file/resource references MUST remain supported, and
unreadable instruction resources MUST fail startup.

#### Scenario: Empty deployment override
- **WHEN** an explicit external catalog contains no servers
- **THEN** no packaged server is added to transport or capability registration

#### Scenario: Missing selected external file
- **WHEN** an explicitly selected external catalog does not exist
- **THEN** the existing no-MCP startup behavior is retained without falling back to packaged servers
