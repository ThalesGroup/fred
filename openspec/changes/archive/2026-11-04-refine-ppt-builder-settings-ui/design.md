# Design

## Context

See `proposal.md` - Why. `FeaturesPage` currently renders the platform settings gear beside "Manage by team" and already uses `platformPanelFor(cap.id)` to decide whether the gear exists. The shared `PptBuilderTemplatePanel` serves both agent form layouts. Its current clear handler removes only a staged file; `usePptBuilderAnalysis` reads `template_sha256` from draft config and already switches to the platform or built-in inventory when the hash is absent. The pod's `validate_config` clears pattern overrides for an absent hash, and `PptBuilderConfig` derives `template_key` from that hash.

## Goals / Non-Goals

**Goals:**
- Keep the source of truth for a platform settings action in the capability UI plugin registry.
- Make the saved-template reset a draft form change that uses the existing agent Save flow.

**Non-Goals:**
- Add a new settings API, change platform-template replacement, or delete historical analysis blobs when an agent stops referencing them.

## Decisions

1. Move the existing gear renderer into a narrow rightmost Settings column in `FeaturesPage`, with a translated header and an empty cell when `platformPanelFor` returns nothing. Keep "Manage by team" in Actions. This preserves the existing drawer, permissions and registry contract. A backend flag would duplicate the frontend panel registration and could advertise a button with no UI.
2. Add a separate "Use platform template" action to the shared PowerPoint template panel when draft config names a saved agent template. It clears the staged file, sets `template_sha256` and `template_key` to null, and empties `overrides`; it leaves vision, variety and plan settings alone. Clearing only a staged file keeps the saved override. The current form callbacks already update draft state, so closing without saving retains the stored template. An immediate hash change lets the existing analysis hook show the default inventory without a new endpoint.
3. Submit the existing config through the normal agent save. Pod validation treats a null hash as default use and drops template-specific edits. No runtime or data migration is needed; old analysis rows remain inert under the current retention behavior. The saved agent's readiness becomes ready through the existing hook.

## Risks / Trade-offs

- [An author mistakes removing the selected file for resetting the saved template] -> Give the two controls distinct labels and test both transitions.
- [A stale template key or pattern edit survives the draft reset] -> Clear all three template-specific fields and assert the submitted payload; pod validation remains the final authority.
- [The new column crowds the table] -> Use a compact fixed track and keep the existing horizontal overflow behavior. No new per-row request is made, so list scale and multi-pod behavior are unchanged.

## Migration Plan

Deploy with PR #3290. Existing agents keep their configurations. Reverting the frontend removes the new controls; agents already reset continue to use the platform default because the stored null hash is supported today.
