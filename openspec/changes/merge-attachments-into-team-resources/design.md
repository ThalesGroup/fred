## Context

See proposal.md - Why. `toolPacks.ts` currently declares two document-access packs. `toolPackLogic.ts` derives corpus and attachment states separately and recomputes their shared capabilities from that pair. `AgentFormModal.tsx` loads an agent's stored selection into form state and sends it on save. The Advanced view edits the same state, including the two `document_access` options.

The earlier `retire-document-reading-pack` change has implemented the shared reading capabilities but has not yet been archived. Its `agent-capability-packs` delta documents the old two-pack behavior. This change follows it and must supersede that behavior when the specs are reconciled.

## Goals / Non-Goals

**Goals:**

- Keep one frontend-owned resource pack and one source of truth in the form's capability selection.
- Apply the combined default to new template seeds and explicit Simple pack activation without changing an existing agent on unrelated edits.
- Let a member deliberately override the attachment option in Advanced across later edits.

**Non-Goals:**

- Change the `document_access` backend contract or the platform administrator's capability grants.
- Rewrite stored agents in bulk or remove the Advanced configuration fields.

## Decisions

### Collapse the resource pack logic to one pack

Remove the attachments registry entry and the two-intent `document_access` model. The remaining resource pack owns the existing corpus and reading ids; turning it on selects available ids and sets `search_attachments_only=false` and `show_attach_files_control=true`. Turning it off removes only the ids owned by that pack. Its checked state follows whether `document_access` is selected, so an Advanced override of one option does not make the entire pack appear off. Keep the `document_access` config object and unrelated capability selection intact apart from the two fields set when the pack is enabled.

The alternative is to keep both intents internally and hide the attachments card. That leaves a hidden switch influencing the pack's state and makes future edits difficult to reason about.

### Apply defaults on creation and explicit pack activation

Use a pure helper to normalize a new template's initial capability selection when `document_access` is preselected. It adds the combined pack's available members and sets both document-access options to the combined defaults. In edit mode, load the stored state unchanged. The Simple pack's on action applies the same defaults; an Advanced edit after that action remains in the submitted state. Subsequent unrelated form edits load and save that explicit Advanced value unchanged.

The alternative is to normalize every edit in the submit builder or initial state. The old corpus-only state is indistinguishable from a deliberate Advanced override after the change, so either alternative would silently undo an explicit setting on a later edit without a persistent migration marker. A deployment migration would change existing agents before their owners edit them.

### Keep the Advanced controls and make copy describe the combined default

The Simple card describes access to team resources and conversation attachments. Its included list shows the capabilities selected by the pack; Advanced continues to expose the detailed `document_access` settings. Update the English and French Help Center sections that currently describe an attachments-only pack and explain that an Advanced override can restrict attachments after the combined default is applied.

## Risks / Trade-offs

- **Legacy agents need an explicit pack action to adopt the bundle:** The pack still reads on when `document_access` is selected, but its old options remain until the member turns the pack off and on. Help Center guidance should explain this transition.
- **An attachment-only agent gains corpus access after pack reactivation:** This is the requested consolidation. Focused tests cover both legacy modes and the team-availability gate.
- **A pack can read on while Advanced has attachments off:** Deriving pack state from `document_access` keeps the views consistent about document access; the pack represents the default bundle, and Advanced is allowed to narrow one option.
- **The preceding unarchived delta describes two packs:** Reconcile the `agent-capability-packs` requirements in merge order, archiving the earlier change first and this change after implementation is verified and merged.

## Migration Plan

Deploy the frontend without a database migration. Existing stored selections remain unchanged on unrelated saves. Re-enabling the pack and saving persists the combined configuration; rolling back the frontend does not undo those saved edits. Add the required English migration note in the implementation PR before it is ready for review.
