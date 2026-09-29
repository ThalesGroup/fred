## Context

See proposal.md - Why. `toolPacks.ts` declares two document-access packs. `toolPackLogic.ts` derives corpus and attachment states separately and recomputes shared capabilities from their combination. The Simple and Advanced views edit the same stored selection, including `document_access` options.

The implemented but unarchived `retire-document-reading-pack` delta describes the current two-pack model and derives each pack's checked state from `document_access` mode. This change supersedes those requirements when the specs are reconciled.

## Goals / Non-Goals

**Goals:**

- Keep the existing Team resources capability set and add the attachments pack's abilities to its Simple switch.
- Preserve Advanced attachment-only selection without implicitly enabling corpus search or corpus-only tools.
- Preserve stored selections for existing agents and derive the new card's state from the full bundle.

**Non-Goals:**

- Change backend document access, administrator grants, or stored agent data on deployment.
- Remove the Advanced `document_access` options or force every agent into the combined bundle.

## Decisions

### Fold the attachments pack into one Simple action

Remove the standalone attachments registry entry and its two-intent pack logic. The remaining Team resources card lists the union of members already granted by the two packs. Its on action selects each available member and sets `search_attachments_only=false` and `show_attach_files_control=true`; its off action removes only members owned by the bundle.

A plain merge of card labels while retaining the old corpus-only toggle would leave attachment upload disabled when a member enables the new pack. The combined on action must set both document-access options.

### Derive checked state from the complete selected bundle

The one pack is checked only when `document_access` is selected, both document-access options match the combined mode, and every admin-available member is selected. An unavailable member does not prevent the pack from reading on. Advanced can still create a partial selection; the included-capability statuses show which members remain active while the Simple switch reads off.

The old two-pack derivation uses `document_access` mode alone because capabilities are shared between independent switches. Keeping that derivation after merging would show the combined pack on for an attachment-only agent, although corpus search and corpus-only tools are off.

### Do not normalize form state on load or unrelated save

New template defaults and existing agent selections enter the form unchanged. Simple pack activation applies the union; Advanced edits change only the chosen capability or option. An existing attachment-only agent therefore retains its mode and capabilities until a member deliberately turns on the combined pack. The same rule preserves an Advanced attachment override across later edits.

Normalizing on form load or submit would turn Advanced attachment-only into corpus access without the member choosing the Simple bundle.

## Risks / Trade-offs

- **Existing agents may show a resource pack switched off while some included capabilities are active:** This accurately represents a partial selection. The included list reflects each active member, and the Help Center explains that Advanced choices can be narrower than the Simple bundle.
- **The prior unarchived delta describes two packs:** Reconcile and archive the earlier change before archiving this one so the durable `agent-capability-packs` spec contains the one-pack rule.
- **Newly enabling the bundle broadens access to both sources:** This is the requested Simple behavior. The updated card copy must name both team resources and attachments.

## Migration Plan

Deploy the frontend without a database migration or stored-agent rewrite. Existing agents keep their selected capabilities and document-access settings. The Simple card may read off for a partial legacy selection; enabling it and saving persists the full bundle. Rolling back the frontend does not undo a member's saved selection. Keep the English migration note aligned with this behavior.
