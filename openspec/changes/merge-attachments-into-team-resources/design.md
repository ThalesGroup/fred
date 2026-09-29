## Context

See proposal.md - Why. `toolPacks.ts` declares two document-access packs. `toolPackLogic.ts` derives corpus and attachment states separately and recomputes shared capabilities from their combination. The Simple and Advanced views edit the same stored selection, including `document_access` options.

The implemented but unarchived `retire-document-reading-pack` delta describes the current two-pack model and derives each pack's checked state from `document_access` mode. This change supersedes those requirements when the specs are reconciled.

## Goals / Non-Goals

**Goals:**

- Keep the existing Team resources capability set and add the attachments pack's abilities to its Simple switch.
- Preserve Advanced attachment-only selection without implicitly enabling corpus search or corpus-only tools.
- Preserve stored selections for existing agents and derive the new card's state from either complete Simple profile.

**Non-Goals:**

- Change backend document access, administrator grants, or stored agent data on deployment.
- Remove the Advanced `document_access` options or force every agent into the combined bundle.

## Decisions

### Fold the attachments pack into one Simple action

Remove the standalone attachments registry entry and its two-intent pack logic. The remaining Team resources card lists the union of members already granted by the two packs. Its on action selects each available member and sets `search_attachments_only=false` and `show_attach_files_control=true`; its off action removes only members owned by the bundle.

A plain merge of card labels while retaining the old corpus-only toggle would leave attachment upload disabled when a member enables the new pack. The combined on action must set both document-access options.

### Offer an attachments-only scope within the active pack

Place a small switch below library scoping in the Simple Team resources card. It writes the existing `search_attachments_only` document-access option and keeps attachment upload enabled. When selected, it withdraws the corpus-only tabular and similarity capabilities while retaining document access and the shared summarization, verbatim, and extraction capabilities. Clearing it reselects the admin-available corpus-only members and restores corpus plus attachment search. Keep library scoping values stored so switching back does not erase a member's folder choices.

Changing `search_attachments_only` alone would leave tabular and similarity tools able to access the corpus, contrary to the switch label. The Simple option therefore updates the selection and document-access config atomically. The Advanced option continues to edit only document access and does not add other capabilities.

### Derive checked state from either complete Simple profile

The one pack is checked when `document_access` and every admin-available shared member are selected, attachment upload is enabled, and the selected corpus-only members match the search scope. With corpus search, all available corpus-only members must be selected. With attachments-only search, tabular and similarity must be absent. An unavailable member does not prevent either profile from reading on. The included-capability statuses continue to show each actual selection.

A complete legacy attachments-pack agent naturally reads on in the attachments-only profile without rewriting stored data. An incomplete Advanced selection remains off. A member who enables the main pack from a partial selection gets the full corpus plus attachments profile.

### Do not normalize form state on load or unrelated save

New template defaults and existing agent selections enter the form unchanged. Simple pack activation applies the union; Advanced edits change only the chosen capability or option. An existing attachment-only agent therefore retains its mode and capabilities; a complete former attachments-pack selection reads on with the attachments-only switch selected. The same rule preserves an Advanced attachment override across later edits.

Normalizing on form load or submit would turn Advanced attachment-only into corpus access without the member choosing the Simple bundle.

## Risks / Trade-offs

- **Incomplete agents may show a resource pack switched off while some included capabilities are active:** This accurately represents a partial selection. The included list reflects each active member, and the Help Center explains that Advanced choices can be narrower than the Simple bundle.
- **The prior unarchived delta describes two packs:** Reconcile and archive the earlier change before archiving this one so the durable `agent-capability-packs` spec contains the one-pack rule.
- **Newly enabling the bundle broadens access to both sources:** This is the requested Simple behavior. The updated card copy must name both team resources and attachments.

## Migration Plan

Deploy the frontend without a database migration or stored-agent rewrite. Existing agents keep their selected capabilities and document-access settings. The Simple card reads on for a complete former attachments-pack selection and off for an incomplete legacy selection; enabling an off pack and saving persists the full bundle. Rolling back the frontend does not undo a member's saved selection. Keep the English migration note aligned with this behavior.
