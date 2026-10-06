## Context

See [proposal.md](proposal.md) for motivation. The frontend currently renders a `mine` root in `TeamResourcesPage`. Knowledge Flow's scoped filesystem uses `users` both at team level (the retired area) and beneath an agent (a supported area), so deleting the constant or every `users` branch would break agent files. The SDK `ToolContext.resolve_template` reads team-level personal files before shared files, while Graph runtime already reads agent-owned files before shared files.

## Goals / Non-Goals

**Goals:**
- Remove every reachable team-level personal-file entry point and align both template helpers with the supported agent/shared lookup order.
- Make the remaining API and UI behavior explicit without changing stored object bytes.

**Non-Goals:**
- Retire the MCP filesystem service or `/fs` routes, which still serve team-shared, agent, and configuration files.
- Migrate, export, or delete existing objects under the retired personal prefix.
- Replace the Deep conversation filesystem or implement durable conversation documents.

## Decisions

1. Reject the top-level `users` sub-area at the shared path resolver, plus synthetic directory, stat, and search paths. Keep the nested agent `users` branch. This removes API access consistently across operations; hiding the frontend tab alone would leave an active backend contract.
2. Remove `read_user_bytes` and `ToolContext.read_user`, then make `ToolContext.resolve_template` read the agent's own bare `templates/` path followed by `shared/templates/`. This follows the existing Graph runtime behavior. Keeping a personal fallback would preserve the retired dependency.
3. Preserve personal-prefix object bytes and avoid a storage migration in this lot. Route rejection is reversible via a code rollback; storage retention or export needs a separately scoped data decision.
4. Keep the resource-space feature flag for the remaining team and agent tabs. Remove only the personal tab, stats query, labels, and obsolete explanatory text.

## Risks / Trade-offs

- [Existing SDK callers use `read_user` or expect personal template overrides] → Treat this as a breaking authoring contract; search repository consumers, update supported examples, and document the new lookup order.
- [A broad `users` removal breaks agent files] → Test both rejection of team-level paths and successful nested agent paths for listing, read, write, stat, and search.
- [Stored personal files become unreachable through the product] → Preserve bytes and identify any operational export need before a later retention decision; do not silently delete them.
- [Backend and frontend deployment versions overlap] → Removing the UI first is harmless; the backend rejects old personal-area requests after deployment. Rollback restores access because objects remain stored.

## Migration Plan

Deploy frontend and backend changes together with the SDK/runtime updates. Existing personal files stay in object storage. If rollback is needed, restore the prior code without data restoration. Decide separately whether retained objects should be exported, migrated, or deleted.
