## 1. Remove MCP exposure

- [x] 1.1 Delete Knowledge Flow's `/mcp-fs` and `/mcp-corpus` mounts without deleting their HTTP controllers; verify route tests show both MCP paths absent and direct `/fs` operations present.
- [x] 1.2 Remove both entries from the packaged MCP catalog; verify agent-pod catalog tests register remaining servers and reject lookup of the retired IDs.

## 2. Remove obsolete contracts and configuration

- [x] 2.1 Remove the two author-facing SDK constants/exports and update active authoring examples and template comments; verify SDK imports/tests and a source search find no active reference.
- [x] 2.2 Remove the MCP-only `filesystem_enabled` flag from Knowledge Flow models/configuration, deployment values and generated schemas; verify configuration and Helm schema checks pass.

## 3. Verify retained consumers and close out

- [x] 3.1 Update tests that used the retired MCPs as fixtures and run affected Knowledge Flow, agent-pod, SDK and configuration tests; verify `list_document_tree` and PPT Filler's direct HTTP `/fs` path remain covered.
- [ ] 3.2 Review the full branch diff against its target and record any findings and dispositions; verify remaining MCP servers, direct corpus APIs, and direct filesystem APIs retain their contracts.
- [ ] 3.3 Reconcile, validate, sync and archive the OpenSpec change after implementation; verify the durable `mcp-capabilities` spec describes the shipped catalog.
