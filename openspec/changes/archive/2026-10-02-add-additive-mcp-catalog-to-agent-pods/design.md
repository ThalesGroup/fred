## Context

`fred-runtime` currently selects either a file catalog or installed providers.
`fred-capability-mcp` now owns only Fred-provided servers, while the Fred pod
needs a deployment-specific place to add other servers.

## Decisions

- Preserve `FRED_MCP_CATALOG_FILE` and the existing `./config/mcp_catalog.yaml`
  as whole-catalog replacement sources. They take precedence for compatibility.
- Otherwise discover installed providers, then read
  `FRED_MCP_EXTERNAL_CATALOG_FILE` or the default
  `./config/mcp_catalog_external.yaml` if present. Construct one `McpCatalog`
  from both server lists so duplicate IDs fail before registration.
- An absent default additive file leaves package discovery unchanged. An
  explicitly selected missing additive file fails startup. An empty file with
  `servers: []` leaves the installed servers unchanged.
- The Fred chart mounts the additive file and sets its path; its default value
  contains no external servers. The production image also copies the app file
  for deployments without that mount.
- The generated Helm values schema validates the external catalog's version,
  server list and core server fields, including deployment overrides.

## Risks / Trade-offs

The two file modes serve different purposes: the legacy path replaces all
servers, while the new path adds servers. Separate environment variables make
that choice explicit. Helm's `servers` list is replaced by a values overlay,
while the runtime combines the rendered file with package providers.
