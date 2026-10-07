## Context

See [proposal.md](proposal.md) for motivation. Knowledge Flow mounts `/mcp-fs` from routes tagged `Filesystem` behind `filesystem_enabled`, and `/mcp-corpus` from `CorpusManager` routes unconditionally. The installed MCP package advertises both. No shipped agent template selects them by default; `document_access.list_document_tree` handles document discovery. Separately, PPT Filler and the runtime use the HTTP `/fs` routes directly for agent assets and output files, so those routes cannot be removed in this lot.

## Goals / Non-Goals

**Goals:**
- Remove the two MCP transports and packaged server identities, including author-facing references and obsolete mount configuration.
- Preserve direct HTTP clients and all remaining MCP registrations.

**Non-Goals:**
- Remove `/fs` HTTP routes, their generated client, or stored files.
- Remove corpus-management HTTP operations or the `document_access` capability.
- Change agent workspace storage or the later `retire-mon-espace` lot.

## Decisions

1. Delete the two `DelegatedFastApiMCP` mounts and catalog entries, leaving the underlying tagged HTTP routers mounted. This targets exactly the agent-facing transport; deleting tagged routers would also break direct clients.
2. Remove the `filesystem_enabled` setting across Knowledge Flow settings, checked-in configuration, chart values and generated schemas because it only gates the deleted MCP mount. Keep filesystem HTTP feature code and configuration that governs actual storage.
3. Remove the two SDK constants and current authoring examples instead of leaving aliases to unavailable servers. Retain all other MCP constants and the ability to supply an external catalog.
4. Update catalog and route tests to assert absence of both MCP transports, presence of retained MCPs, and continued HTTP `/fs` access.

## Risks / Trade-offs

- [Persisted agent selections might name a retired server] → The user has confirmed these servers are not used by agents; verify local/static defaults and ensure unknown selections fail clearly rather than silently falling back.
- [A broad search-and-delete removes `/fs` HTTP functionality] → Review direct runtime and PPT Filler paths and keep their tests passing.
- [Generated schemas drift after removing the mount flag] → Regenerate the relevant configuration schemas from source and validate chart/config loading.

## Migration Plan

Deploy the pod catalog and Knowledge Flow mount removal together. Previously saved references to retired server IDs require selection cleanup if found in an environment; no storage migration is required. Rollback restores MCP exposure without restoring data because this change does not mutate files.
