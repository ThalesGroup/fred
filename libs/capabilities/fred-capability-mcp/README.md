# MCP capability catalog and instructions

Installing this package supplies Fred's internal MCP servers at pod startup through
its `fred.mcp_catalogs` entry point (`fred_capability_mcp:load_catalog`). The loader
uses `fred_sdk.resources.mcp`; capability construction, composer controls and
prompt groups live in `fred_sdk.contracts.capability.mcp`. The package has no
`fred-runtime` dependency.

The runtime resolves one catalog for transport and capability registration.
`FRED_MCP_CATALOG_FILE` or an existing `./config/mcp_catalog.yaml` replaces all
packaged servers. Otherwise it combines installed providers with the optional
`FRED_MCP_EXTERNAL_CATALOG_FILE` or `./config/mcp_catalog_external.yaml` file.
Duplicate server IDs fail startup.

The wheel includes one `mcp_catalog.yaml` with the three MCPs provided by
Fred / Knowledge Flow. Third-party MCP servers are not defined by this package.

Internal HTTP MCPs declare their backend and a path relative to its API:

```yaml
service: knowledge_flow
path: mcp-tabular
```

`fred_sdk.contracts.services` defines `FredService` and `ServiceEndpointsPort`.
At boot, the runtime passes `ConfiguredServiceEndpoints` to each catalog loader.
Its `get_base_url(service)` reads `ai.knowledge_flow_url` or
`platform.control_plane_url`, preserving the configured scheme, host, port and API
prefix. For example, `https://kf.example:9443/custom/v2/` produces
`https://kf.example:9443/custom/v2/mcp-tabular`. No address is stored in the
package catalog. Local document search is supplied by the native `document_access`
capability; the MCP catalog no longer advertises that tool or the unimplemented
GitHub adapter. Local tools use capabilities rather than an MCP transport.

External catalogs may use the same references by passing `services` to the SDK
loader, or retain a concrete `url`. Do not combine `service` with `url`.
Unknown services, missing addresses and invalid HTTP paths fail catalog loading.
SDK-only callers supply their own implementation of the port; no runtime import
or network discovery is required.

The wheel also includes `prompts/tabular.md`, the default pod's tabular instructions.

Deployment-owned catalogs can reference these instructions using:

```yaml
prompt_file: pkg://fred_capability_mcp/prompts/tabular.md
```

Inline `agent_instructions` remains supported. File references also accept
absolute paths or paths relative to the catalog. A packaged catalog resolves
relative paths within the package, including when imported from a wheel.
Declare only one instruction source; unreadable resources fail startup.

`fred-agents` installs this package locally and in its image; no copied catalog
or checkout symlink is needed. The Fred chart mounts an additional external
catalog while the installed package supplies its internal servers. Other pods
can provide their own MCP catalogs through the SDK/runtime interfaces. No extra
selectable wrapper capability is introduced: enabled servers retain their IDs.
