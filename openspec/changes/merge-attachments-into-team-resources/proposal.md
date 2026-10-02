## Why

Tracking: https://github.com/ThalesGroup/fred/issues/2837

The Simple capabilities view presents team resources and conversation attachments as separate packs even though both configure document access. One combined pack makes the bundled choice clear while preserving independent configuration in Advanced.

## What Changes

- Remove the standalone "Conversation attachments" card from Simple. Keep the existing "Team resources" members and add the attachment abilities to that pack.
- Enabling the combined pack in Simple selects every available capability in the union and configures document access for corpus plus attachments (`search_attachments_only=false`, `show_attach_files_control=true`).
- A switch below library scoping in the Simple pack selects attachments-only search. It keeps the shared reading capabilities but keeps available tabular access for conversation spreadsheets and withdraws similarity access; clearing it restores the available corpus members. The main pack switch stays on for either complete profile.
- Advanced remains granular. Selecting attachments there does not automatically add corpus search, tabular access, similarity search, or the shared reading capabilities. Incomplete Advanced selections leave the Simple pack off.
- **BREAKING (Simple view):** existing agents are not migrated. An agent that used only the former attachments pack keeps those selected capabilities and its attachments-only mode; a complete former attachments-pack selection reads on with the new attachments-only switch selected, while an incomplete selection reads off. Update focused tests, French and English copy, and Help Center guidance.

## Capabilities

### New Capabilities

- `agent-capability-packs`: the Simple view's combined resource pack behavior. The same capability path is introduced by the already implemented, still unarchived `retire-document-reading-pack` change; this delta follows that change and must be reconciled against it before archive.

### Modified Capabilities

None. No current spec under `openspec/specs/` covers agent capability packs yet.

## Impact

Frontend pack registry and logic, tests, translations, and English and French Help Center pages. No backend capability, public API, database, or stored agent migration.
