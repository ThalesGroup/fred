# Native Tabular capability

This package installs `TabularCapability` through `fred.capabilities`. It owns
`prompts/tabular.md`, configuration validation and the shared MCP composer controls.
Its stable ID is `mcp-knowledge-flow-mcp-tabular`; selections, configuration and
chat controls all use that ID.

Enable the capability in **Features > Capabilities**, within the usual organization
and space policy, then select its own card on a General or Deep assistant.
This selection is independent of the document-reading packs. There is no
connection to create, test, publish or activate in **Features > MCP**. That page
manages external servers only. Knowledge Flow availability is not an administrative
gate: a service outage fails execution without changing the capability permission.

At turn admission, Control Plane supplies the internal endpoint derived from
`platform.knowledge_flow_url` plus `/mcp/tabular`. The Agent Pod checks it against
`ai.knowledge_flow_url`, then uses the existing MCP transport with the admitted
user's delegation and document context. The trusted service's tools are discovered
at execution; no connection UUID or reviewed external inventory is required.
External MCP connections retain their explicit publication and credential rules.

This package contains no endpoint catalogue, credential or network discovery.
The runtime rejects Knowledge Flow entries in pod MCP catalogues. The independent
SDK catalogue loader remains available for other consumers; `document_access`
continues to use its native SDK/REST adapter.

See [Control Plane's contract and reception procedure](../../../apps/control-plane/README.md#trusted-knowledge-flow-tabular).
