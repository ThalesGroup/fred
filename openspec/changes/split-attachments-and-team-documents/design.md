## Context

See proposal.md for the motivation and the relation to #2837.

Current state:

- `DocumentAccessConfig` (`libs/capabilities/fred-capability-document-access/fred_capability_document_access/capability.py`) holds `show_attach_files_control` and `search_attachments_only`. `chat_controls()` emits `attach_files` from the first. When both are on, it also suppresses the `document_scope` control. `tools()` passes `attachments_only` to `DocumentSearchPort.search` and drops `list_document_tree` in that mode. A `model_validator(mode="before")` (`_upgrade_legacy_slices`) already upgrades two earlier key shapes.
- `DocumentSearchAdapter.search` (`libs/fred-runtime/fred_runtime/integrations/v2_runtime/adapters.py`) starts from `get_vector_search_scopes(runtime_context)`. When `attachments_only` is set, it overrides the result to `(session=True, corpus=False)`. The per-turn `corpus_only` choice maps to `(False, True)`, `general_only` to `(False, False)` (short-circuited), and `hybrid` to `(True, True)`.
- Stored capability configs are envelopes of the form `{schema_version, config}`. A save sends the submitted values through pod validation and persists the result of `model_dump`, so removed keys disappear on save. Platform import (`control_plane_backend/import_export/importer.py`) and the agent form (`extractCapabilityConfigValues` in `AgentFormModal.tsx`) both handle the raw stored dict. Legacy keys therefore reach the frontend until the agent is saved again.
- `ChatControlItem.params` is a `dict[str, Any]`. `RagScopeControlParams` is not part of any generated OpenAPI client, and the frontend declares its own `RagScopeControlParams` in `RagScopeControl.tsx`.
- The Simple view (`toolPacks.ts`, `toolPackLogic.ts`, `DocumentAccessPackOptions/`, wired in `AgentFormBody.tsx`) has one `resourceBundle` pack. It provides `applyPackToggle`, `applyResourceSearchScope` and `derivePackChecked`, which special-case `search_attachments_only`.
- The Advanced card renders the manifest's `config_fields` in order, with `ui.group` dividers and `ui.visible_when`. Save-blocking errors go through `capabilityBlockingErrors` in `AgentFormModal.tsx`. This is the mechanism the PowerPoint template upload already uses.

## Goals / Non-Goals

**Goals:**

- One positive setting per source, read the same way in every path: save, read, copy, import, chat controls and tools.
- The per-turn RAG scope can only narrow the agent's sources.
- Simple packs map one-to-one to sources. Advanced stays granular.

**Non-Goals:**

- Splitting `document_access` into two backend capabilities or two search tools. That would need evals of tool selection.
- A general agent scope ceiling for summarize and other document ports. That question stays open in `CAPABILITY-SCOPE-CEILING-RFC.md`.
- Any Knowledge Flow, ranking, or database change.

## Decisions

### D1. Compatibility through the existing before-validator

Extend `_upgrade_legacy_slices` with the mapping in `specs/document-access-sources`. Mapping applies only when neither new key is present; legacy keys are removed on validation. This covers stored values, imports and submitted legacy form values. The manifest version is `0.2.0` to invalidate the control-plane chat-controls cache. This manifest version is separate from the distribution package version.

### D2. Both sources off: rejected by the backend, prevented by the form

A `model_validator(mode="after")` raises when both sources are off. Pod validation returns the existing `capability_config_invalid` error, so the save fails with 422. No legacy shape maps to both-off, so a stored agent cannot be suspended by this rule. The form never submits that state:

- In the Simple view, turning off the last pack deselects `document_access` (spec "Turning off the last document pack deselects document access").
- In the Advanced view, turning off the last source deselects the card too, and resets both sources to on so that selecting it again starts from the default. There is no save-blocking error to show.

Alternatives rejected:

- Silently treating both-off as both-on hides a member's choice.
- Server-side deselection is not possible: config validation cannot change the capability selection.
- A new "disable the last switch" UI hint would add SDK surface for one field.
- A save-blocking error in Advanced (first implementation): the member had to fix a state the form could avoid on its own; replaced by deselection after developer review.

### D3. Replace the port's `attachments_only` with two ceilings

`DocumentSearchPort.search(..., include_attachments: bool = True, include_team_documents: bool = True)` replaces `attachments_only`. The adapter computes:

`session = turn_session AND include_attachments`, and `corpus = turn_corpus AND include_team_documents`.

If both are false, the adapter returns no hits without calling Knowledge Flow, the same way `general_only` does today. The capability passes `config.attachments` and `config.team_documents`.

Why: a team-documents-only agent needs a way to exclude the session scope, which `attachments_only` cannot express. Two ceilings ANDed with the turn are the "narrow only" rule stated directly. This matches the direction of `CAPABILITY-SCOPE-CEILING-RFC.md` §5 Tier 1, where `attachments_only` becomes derived from a ceiling, without building its general descriptor.

Alternatives considered:

- Keep `attachments_only` and add `corpus_only`: two negative flags plus an invalid combination.
- Pass the config to the adapter: this breaks the port doctrine, under which the capability passes scope parameters only.

`attachments_only` is removed now, including the resolver and warning state. The developer explicitly accepts that old callers fail and requests patch increments for all publishable libraries. Use `include_attachments=True, include_team_documents=False` for an attachments-only call. Preserve stored-config compatibility in D1.

### D4. Document-only answers use every enabled document source

Keep the wire value `corpus_only`, but label it "Documents only" / "Documents uniquement". Like `hybrid`, it searches session attachments and the team corpus, bounded by explicit turn flags and the agent's source ceilings. `general_only` skips document search. Document-only mode asks the agent to answer from document evidence without filling gaps from general knowledge.

Change the shared `get_vector_search_scopes` default so the document-access adapter, builtin search and MCP search agree. The existing explicit turn scope overrides remain intact. Offer all three choices for attachments-only, team-only and both-source agents. Keep the generic optional `RagScopeControlParams.options` contract and composer support for restricted controls from other providers.

### D5. Advanced field order and visibility come from the manifest

Put `attachments` and `team_documents` first, in a new `sources` group. Give `show_library_selection`, `bind_libraries`, `library_tag_ids` and `show_document_selection` `ui.visible_when="team_documents"`. `library_tag_ids` keeps its own `bind_libraries` condition. The current renderer accepts a single key, so it is shown only when both conditions hold. The current renderer (`CapabilityCard.tsx`, `TuningFieldRenderer.tsx`) checks only the single sibling a field names. `library_tag_ids` therefore keeps `visible_when="bind_libraries"`. That is sufficient because `bind_libraries` itself is hidden while team documents is off, and the bound ids are inert in that state (spec). The edge case to test: `bind_libraries` is stored true and team documents is then turned off. The picker would still render under a hidden switch. If it does, `CapabilityCard`'s visibility filter is extended to hide a field whose gating sibling is itself hidden. This is a one-line transitive check, and no new hint is added.

This keeps the Advanced UI driven by the manifest and adds no frontend special case.

### D6. Simple packs: two registry entries plus a source key

Replace `resourceBundle?: true` on `ToolPack` with `documentSource?: "attachments" | "team_documents"`. The packs `attachments` and `team_documents` list their members in `enablesCapabilityIds`.

`toolPackLogic.ts` is rewritten around the sources:

- Turning a pack on adds its available members and sets its source to true. Other sources are kept, or both start false when `document_access` was not selected.
- Turning a pack off sets its source to false. If the other source stays on, it removes only members the other pack does not grant: similarity when Team documents goes off, and nothing when Attachments goes off. When it was the last source, it removes `document_access` and every member of both packs.
- A pack's checked state is `document_access` selected plus that pack's source.

The form receives raw stored dicts (Context). A small pure helper, `normalizeDocumentAccessConfig`, applies the D1 mapping once in `extractCapabilityConfigValues`. It replaces the legacy keys with `attachments` and `team_documents` in form state, so the Simple logic and the Advanced card (`visible_when`, switch values) only ever see the new keys. This translates key names only and grants no access the backend would not also grant, so it respects the "no rewrite on load" rule. An unrelated save then submits the same meaning under the new keys. `applyResourceSearchScope` and the `search_attachments_only` switch in `DocumentAccessPackOptions` are deleted. `DocumentAccessPackOptions` keeps only library binding and is rendered for the Team documents pack.

Alternatives considered:

- Rewriting stored configs with an Alembic data migration would remove the frontend helper. It would not cover bundles imported later, and it adds a cross-service migration for a capability-owned blob.
- Keeping the single pack with a positive sub-switch keeps the confusion this change addresses.

### D7. Spec sequencing with the two unarchived changes

`agent-capability-packs` exists only as deltas in `retire-document-reading-pack` (task 5.4 open) and `merge-attachments-into-team-resources` (task 4.6 open). Both are implemented and merged on `swift`. Archive in this order before implementing this change:

1. `retire-document-reading-pack`.
2. `merge-attachments-into-team-resources`, reconciling its "one pack" requirements against the first archive, which is its own task 4.6.
3. This change's delta headers are re-checked against the resulting `openspec/specs/agent-capability-packs/spec.md`.

`openspec validate --strict` already reports that archiving this change's MODIFIED/REMOVED operations needs that spec to exist. Extending `merge-attachments-into-team-resources` instead of creating this change was rejected. That change is shipped, its issue is closed, and its verification evidence describes delivered behavior. This change also reverses its central decision and adds backend scope, so reopening it would mix two contracts.

## Risks / Trade-offs

- [Risk] External SDK callers using `attachments_only` break immediately. → Required action: migrate to the two source keywords and upgrade SDK/runtime together; dependency floors and the migration note make this requirement explicit.
- [Risk] Legacy `show_attach_files_control=false` agents stop searching the session scope. → Mitigation: those agents never had a paperclip. Session-scoped documents could only come from earlier turns under another configuration. The migration note states the change.
- [Risk] The mapping exists in two places (Python validator, TypeScript helper). → Mitigation: both carry the same table-driven tests over the three legacy shapes. A follow-up removes both once no stored legacy keys remain. A control-plane query can count these agents.
- [Risk] The control-plane chat-controls cache key `(capability_id, version, config_hash)` would stay unchanged for legacy envelopes while the computed controls change (the `rag_scope` options), and the control plane is not restarted when only the agent pod is deployed. → Mitigation: the manifest version moves to 0.2.0, which changes the key; stored slices still validate through the default `upgrade_config`.
- [Trade-off] `corpus_only` is retained as the wire value for compatibility, while its user-facing meaning becomes all enabled document sources.

## Migration Plan

Upgrade SDK/runtime and document-access consumers together. Migrate external `attachments_only` calls before deployment. Stored agents keep working through D1 and are rewritten on their next save. There is no database or Knowledge Flow migration. On rollback, revert the library set and adapted callers together; re-saved agents need their document-source settings checked because the old runtime ignores the new keys.

## Reviewer decisions (confirmed by dimitri-tombroff, 2026-10-08)

1. Remove `attachments_only` in this PR. The developer explicitly accepts this API break and requests patch version increments rather than waiting for a minor or major release.
2. Include attachments in `corpus_only` when both sources are enabled. Use all enabled sources, preserve source ceilings, and update the labels and Help Center to describe document-only answers.
3. Raise dependency floors in this PR. Increase every publishable library under `libs/` by one patch (Python core `4.4.2`, each capability's next patch, frontend `0.1.1-alpha.0` retaining its alpha channel), refresh consumer lockfiles and require the new SDK/runtime where the changed contract needs them. The maintainer will publish the libraries immediately after PR merge, before consumers upgrade. This prepares versions; it does not publish packages or tag a code/chart release.

## Deferred (separate issues)

- Search hit provenance (attachment vs team document) is not exposed to the model.
- A per-turn document pick may hide attachments from the search.
- Tabular access to attachments is authorized by owner rather than by session.
- Graph and Deep agents may not receive the conversation's attachment list.
- Splitting `document_access` into two backend capabilities or two search tools needs evals.
- Summarize, verbatim and extract are not bounded by the agent's sources (`CAPABILITY-SCOPE-CEILING-RFC.md`).
