# Tabular business contribution

This package installs `TabularCapability` through `fred.capabilities`. It owns
`prompts/tabular.md` and the shared MCP composer controls. It has no runtime
dependency, connection URL, credential, technical catalog or network discovery.

Its stable author ID `mcp-knowledge-flow-mcp-tabular` declares
`mcp_service: knowledge_flow_tabular`. An author can use that dependency in
`default_capability_ids` without embedding a deployment UUID. Control Plane
resolves it to the single published, enabled and permitted central offer for a
compatible template. A missing service leaves an explicit unavailable dependency;
it never falls back to a pod catalog. The dependency is not a second native offer
or a second business permission. Configuration and chat-control evaluation remain
owned by this package; saved selections/configuration use the central offer ID.

Platform administrators declare, discover, publish and enable the trusted
Knowledge Flow connection through the existing MCP page. Organization and local
permissions remain separate. Control Plane uses its shared M2M identity for
technical discovery. Each executing turn uses its existing delegated workload
provider and document context. The full configuration and unexecuted local
reception procedure are in [Control Plane's README](../../../apps/control-plane/README.md#trusted-knowledge-flow-tabular).

The former Tabular YAML connection and fictitious Prometheus entry were removed.
Reinstall/sync the pod's editable dependencies after updating this package so
installed entry-point metadata reflects the new `fred.capabilities` entry point.
The runtime rejects migrated KF entries in legacy pod catalogs at startup.

The SDK catalog loader and `McpCapability` adapter remain for independent SDK and
non-migrated pod catalog consumers. `document_access` continues to use its own
native SDK/REST adapter; it is not an MCP connection. This implementation still
requires the documented functional reception; generation is not acceptance.
