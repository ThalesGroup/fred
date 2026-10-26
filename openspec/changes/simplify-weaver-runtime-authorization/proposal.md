## Why

Weaver discovers Fred agent templates but does not yet persist their configured instances or provide the management/preparation routes consumed by Swift's existing form and chat. Restore Custom Assistant through the Rust Control Plane while replacing ReBAC and admission; preserve the working Swift agent, configuration and execution behavior.

## What Changes

- **BREAKING**: replace Swift authorization and context resolution in the Weaver Python libraries. No compatibility flags, old/new dispatch, fallback endpoints, legacy identity aliases or data migration in this change. Swift maintenance stays on its branch.
- Reimplement the missing managed-agent responsibilities in Rust: space-scoped template projection, instance persistence and CRUD, configuration validation, execution preparation and runtime resolution. Preserve existing tuning/capability contracts and form behavior, with model ownership/selection replaced under decision 5e; do not replace them with a name/prompt-only schema or a template-only execution shortcut.
- Preserve Swift's ownership split for chat: Control Plane stores lightweight session metadata and routes the UI to the runtime; the runtime owns messages, checkpoints and execution. Restore the required metadata/preparation APIs in Rust instead of redesigning the chat.
- Consume the Control Plane's published PostgreSQL/OpenFGA binding read-only; never create a store or synchronize a schema from the runtime.
- Resolve canonical execution context through Control Plane, preserving existing authenticated delegation and credential providers. Authorize the run with `can_read(user, space)` and `can_use(space, template)`.
- Resolve complete turn authority once through the existing Control Plane call, then enforce it locally for every invocation, retry and descendant. Revocation/decommissioning takes effect at the next turn; no additional per-invocation authority requests or five-minute revocation guarantee. Explicit cancellation and JWT renewal remain separate.
- In the subsequent documentary lot, replace Knowledge Flow HTTP search/read dependencies with a shared local document-access primitive: space-and-ancestor scope, storage prefilter, and grouped PostgreSQL publication/lifecycle verification. No document tuples or per-document OpenFGA checks.
- Add complete installed-tool inventory per configured pod and organization Manage-protected read/refresh, preserving provenance, withdrawal and unavailable observations. Organization model policy follows decision 5e; capability configuration saving remains separate.
- Preserve Swift capability declarations, registry, effective configuration, the model routing engine, clients and credential renewal. Replace agent model catalog ownership and manual profile choices as specified in decision 5e; preserve Knowledge Flow embeddings and processing. Template activation cannot broaden organization model permission; no independent capability/model ReBAC catalogue is introduced. Missing dependencies still prevent activation/execution.
- **Acquired model direction (2026-10-26):** Control Plane owns an API-discovered platform inventory keyed by `(source_id, upstream_model_id)`, independent of pods. Platform owns destinations/credentials; pods execute. No manual per-pod model catalog or source without compatible discovery. Decision 5e records accepted source/authentication, qualification, outage and selection decisions; the later accepted M4 arbitration uses one complete resolver call per turn, with no dedicated runtime SQL authority view/grant. Initial inference support is OpenAI-compatible. M1 source configuration/discovery/persistence and M2 organization inventory/refresh/policy APIs are implemented locally, without functional validation. M3 instance recommendations/options and resolver data are also implemented locally; M4-M5 remain separate. No runtime model enforcement is claimed.
- Remove replaced paths and their configuration/registrations as each lot lands. Keep reusable credential, storage and lifecycle mechanisms.

The 2026-10-25 sequencing decision prioritizes core Weaver ReBAC for the next
increment. Swift global admission filtering remains required but is deferred to a
subsequent lot, not a prerequisite for this increment. See design decision 2a and
task 4.1; do not add temporary feature refusals or infer a replacement global policy.

## Capabilities

### New Capabilities

- `weaver-runtime-authorization`: managed execution and local document retrieval under canonical Weaver identity, space, template and publication rules.

### Modified Capabilities

None mechanically rewritten in this proposal. Existing Swift `team-resource-spaces` and `document-storage` specs describe Knowledge Flow API contracts and are not proof of Weaver behavior. This change replaces the search/read path for the scoped Weaver journey; unrelated artifact, attachment and tabular workflows are not silently ported. Reconcile conflicting requirements explicitly when integrating the completed scope, not by claiming that both architectures remain supported.

## Impact

Owners: Rust Control Plane for existing managed-instance and session-metadata behavior under Weaver permissions; frontend for generated-client/binding adaptations to the existing form/chat; `fred-core` for shared checks and later local document access; `fred-runtime`/`fred-pod` for admission and security wiring; `fred-sdk` for canonical context. Reuse the agent definitions, execution engines, configuration contracts, credential providers, model router, event stream and checkpoint/history stores.

The next delivery is Bob in team fredlab, organization TSN, creating/editing a `fred.github.assistant` instance through the existing form, using its stored configuration, exchanging streamed messages, and reopening/resuming its conversation without the Python Control Plane or Knowledge Flow API. Its existing empty default capability selection makes this first path independent of document retrieval. This is an acceptance path, not permission to simplify its configuration model or remove supported form features. Unported dependencies remain explicitly unavailable; the form and selection logic are retained for their subsequent connection.

Only Custom Assistant, Custom Planning Assistant (`fred.github.deep_assistant`) and Test Assistant (`fred.github.test_assistant`) are migration targets. Rico and other specialized agents are not prerequisites. Local document access on the same Custom follows the first lot; Planning then reuses the common boundary, including its filesystem and child execution. Test Assistant accompanies the supported scenarios without requiring all of its real-tool branches to be available immediately.

Out of scope: data migration/import/reset, applied migration edits, OpenFGA model replacement, remote MCP, new instance-creation or conversation product UX, document writes, marketplace/publication, and a general rewrite of capabilities, model routing or plugins. Additive schema changes for instance/session metadata are in scope; existing migration history remains intact. Preserving the existing form is in scope, rebuilding every adjacent Swift administration feature is not. No signed execution grant, authorization HTTP proxy per tool, or new authorization service.

Implementation proceeds only in explicitly requested increments. Existing dirty changes are preserved. Dimi owns dynamic validation; M1-M3 authorize scoped quality checks, contract generation and technical compilation, but no tests, applied migrations, deployments, commits or pushes.
