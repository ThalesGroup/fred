## Why

Tracking: https://github.com/ThalesGroup/fred/issues/2837

The Simple capabilities view presents team documents and conversation attachments as separate packs even though both depend on `document_access`. A single resource pack makes document access a clear choice for agent creators.

## What Changes

- Remove the standalone "Conversation attachments" pack from the Simple view. The "Team resources" pack enables both team corpus access and conversation attachments with one switch.
- When the combined pack is enabled, select its currently available corpus and reading capabilities and configure `document_access` for corpus plus attachments (`search_attachments_only=false`, `show_attach_files_control=true`).
- **BREAKING (form behavior):** existing corpus-only and attachment-only agents keep their stored behavior on deployment and unrelated edits. Re-enabling the resource pack in Simple adopts the combined defaults. An explicit attachment setting change in Advanced remains durable across later edits.
- Keep individual capability and `document_access` settings editable in Advanced. Update pack state derivation, focused tests, French and English copy, and Help Center guidance.

## Capabilities

### New Capabilities

- `agent-capability-packs`: the Simple view's combined resource pack behavior. The same capability path is introduced by the already implemented, still unarchived `retire-document-reading-pack` change; this delta follows that change and must be reconciled against it before archive.

### Modified Capabilities

None. No current spec under `openspec/specs/` covers agent capability packs yet.

## Impact

Frontend agent form, pack registry and logic, tests, translations, and English and French Help Center pages. No backend capability, public API, or database change. Existing stored agent selections change only when the member changes the resource pack or Advanced settings and saves.
