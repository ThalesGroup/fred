## ADDED Requirements

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
- **WHEN** an internal inprocess MCP identifies Knowledge Flow without an MCP path
- **THEN** its transport and provider remain unchanged and no remote MCP URL is added

#### Scenario: Invalid service reference
- **WHEN** a catalog names an unknown service, combines a service reference with a
  concrete URL, omits the required HTTP path, or references an unconfigured service
- **THEN** catalog loading fails explicitly without falling back to localhost

#### Scenario: Literal deployment override
- **WHEN** a selected external catalog supplies a concrete MCP URL
- **THEN** loading retains that exact URL regardless of the pod's service addresses
