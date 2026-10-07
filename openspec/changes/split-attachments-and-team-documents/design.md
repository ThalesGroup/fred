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

### D1. Compatibility through the existing before-validator, no manifest version bump

Extend `_upgrade_legacy_slices` with the mapping in `specs/document-access-sources`. Mapping applies only when neither new key is present. The legacy keys are then popped so that they never round-trip. The manifest `version` stays `0.1.0`.

Why not bump the version and override `upgrade_config`? That hook runs only on a `schema_version` mismatch at read time. Legacy keys also arrive in values submitted by the form on an unrelated save, in imported bundles stored verbatim, and in chat-controls evaluation of same-version slices. The before-validator covers all of these paths in one place. `AUTHORING.md` currently says that a rename should bump the version and override `upgrade_config`, and keeps an explicit pre-GA "no bump" policy. This change follows the no-bump policy and adds one sentence to `AUTHORING.md`: a same-version rename may be absorbed by a before-validator when submitted values can still carry old keys.

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

`attachments_only` stays accepted as a deprecated alias: when given, it sets `include_attachments=True, include_team_documents=False` and logs a deprecation warning once per process. No caller breaks, so the change stays `patch`. The alias is temporary; when to remove it is a reviewer decision (see "Reviewer decisions").

### D4. Filter `rag_scope` choices in the capability, honour them in the composer

`RagScopeControlParams` gains an additive `options: list[RagScopeName] | None` field (`None` means all choices). `chat_controls()` drops `corpus_only` when `team_documents` is off and clamps a `default_rag_scope` that is no longer offered to `hybrid`.

`RagScopeControl.tsx` renders only the offered options. `useComposerSettings` resets a persisted per-session `ragScope` that is no longer offered to the control's default. Without that reset, a remembered `corpus_only` on an attachments-only agent would search nothing under D3.

No other choice becomes impossible:

- `hybrid` covers whichever sources are on.
- `general_only` never searches.
- With attachments on and team documents on, `corpus_only` ("Your documents") excludes attachments today. Whether it should include them is a reviewer decision (see "Reviewer decisions"); the implementation follows that decision before merge.

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

- [Risk] SDK consumers outside this repo call `DocumentSearchPort.search(attachments_only=...)`. → Mitigation: the keyword stays as a deprecated alias with a warning, so callers keep working. Out-of-tree implementers of the port would need the two new keywords; none is known.
- [Risk] The alias stays forever. → Mitigation: its removal is an explicit reviewer decision recorded in the PR, and the migration note announces the deprecation.
- [Risk] Legacy `show_attach_files_control=false` agents stop searching the session scope. → Mitigation: those agents never had a paperclip. Session-scoped documents could only come from earlier turns under another configuration. The migration note states the change.
- [Risk] The mapping exists in two places (Python validator, TypeScript helper). → Mitigation: both carry the same table-driven tests over the three legacy shapes. A follow-up removes both once no stored legacy keys remain. A control-plane query can count these agents.
- [Risk] The chat-controls cache key `(capability_id, version, config_hash)` is unchanged for legacy envelopes, while the computed controls change (the `rag_scope` options). → Mitigation: the cache is in-process LRU with a pod restart on deploy. It is not persisted, so the new code computes fresh controls.
- [Trade-off] With both sources on, "Your documents" still excludes attachments, which is the existing behavior. The label is not changed here.

## Migration Plan

Deploy normally. There is no database or Knowledge Flow change and no operator action. Stored agents keep working through D1. Each agent is rewritten to the new keys on its next save. Rolling back to the previous version is safe for agents that were not re-saved. A re-saved agent stores only the new keys, which the previous version ignores, so it falls back to the defaults (paperclip on, corpus and attachments searched) until it is re-saved. The migration note records this rollback caveat. The version impact is `none` (patch): the SDK keyword is kept as a deprecated alias.

## Reviewer decisions (must be settled in PR review, expected reviewer: dimitri-tombroff)

The PR description asks the reviewer to decide both points. No half-decision is merged: the implementation is adjusted to the answer before merge, and this section records it.

1. **When to remove the deprecated `attachments_only` alias.** It is kept now so nothing breaks (patch). Options: remove it in the next minor release with an announcement in its migration note, or keep it until a named major release. Developer's opinion: do not leave it long.
2. **Should "Your documents" (`corpus_only`) include attachments when both sources are on?** Today it excludes them, and its label does not say so. Developer's opinion: include attachments. If the reviewer agrees, `corpus_only` on a both-sources agent maps to `(session=True, corpus=True)` minus the general answer, and the label and Help Center wording follow; this changes the per-turn semantics described in D4.

## Deferred (separate issues)

- Search hit provenance (attachment vs team document) is not exposed to the model.
- A per-turn document pick may hide attachments from the search.
- Tabular access to attachments is authorized by owner rather than by session.
- Graph and Deep agents may not receive the conversation's attachment list.
- Splitting `document_access` into two backend capabilities or two search tools needs evals.
- Summarize, verbatim and extract are not bounded by the agent's sources (`CAPABILITY-SCOPE-CEILING-RFC.md`).
