## Why

Issue [#2845](https://github.com/ThalesGroup/fred/issues/2845) exposes truncated authorization inventories and incomplete folder deletion. The developer chose a simpler team-scoped corpus model instead of optimizing per-document grants or adding compensating recovery systems.

## What Changes

- **BREAKING:** one corpus document belongs to exactly one folder; folders and documents inherit the owning team's rights. No folder/document sharing or cross-team moves.
- All team members can read; only editors can mutate. A personal team's owner can manage their own corpus.
- Users explicitly create/select a folder before ingestion. No automatic default folder. Conversation attachments remain separate from the corpus.
- Replace corpus-wide authorization enumeration with team authorization and database-scoped inventory. Remove corpus document and human folder relation writes after migration. Preserve the approved source-account grant on its synchronization root.
- Reject deletion while ingestion is active in the subtree. Accepted deletion hides the tree, rejects new writes and cleans it through Temporal.
- Accept temporary vector-search results until cleanup finishes; do not add result revalidation solely for deletion concurrency.
- Fail explicitly when required components are unavailable. No Fred-side fallback queues, automatic redelivery or compensating sweeper.
- **BREAKING:** retire the older knowledge-flow prompt/template/chat-context resource API and its MCP exposure, storage wiring and configuration. Also retire the unused direct report creation API and its MCP mount. Preserve the current control-plane prompt library, conversation attachments and existing report documents. Existing legacy data must pass an explicit stop-and-review migration gate; no silent deletion or conversion.
- The ingestion fallback removal is local WIP. After an unconfirmed start error, show an explicit error and retain reservations; the developer accepts manual intervention if no execution exists. No automatic redelivery or release.

## Capabilities

### New Capabilities

- `corpus-access-integrity`: team-scoped corpus access, single-folder membership, explicit admission conflicts and asynchronous deletion. Reuses the existing change's capability name.

### Modified Capabilities

None declared at this stage. Discovery must check intersecting published contracts before finalizing implementation scope.

## Impact

Knowledge-flow corpus routes, SQL stores, ingestion, Temporal tasks, vector/tabular retrieval, frontend folder actions, import/source synchronization and shared authorization callers. The older knowledge-flow non-document resource subsystem is now explicitly included for retirement. Other consumers are not automatically included. Team/agent/tool admission remains distinct.

## Planning status

The developer explicitly authorized completing the implementation in dependency order. Confirmed business rules are captured in the delta spec; design.md records remaining technical boundaries. Ask before deciding an unresolved behavioral, data-migration or complexity choice, while continuing independent approved work. tasks.md records actual completion and validation; authorization to proceed is not evidence that the change is ready to publish. This change supersedes the earlier multi-folder and compensating-journal experiments.

Frontend upload-only mode and existing request splitting remain unchanged. Conflict admission is atomic per backend request. Broader frontend/public API redesign is deferred to a separate review after this PR.
