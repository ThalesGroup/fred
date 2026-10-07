## Why

Tracking: GitHub issue #2999.

The agent form conflates two independent decisions: "the agent can use files attached to the conversation" and "the agent can search the team's documents". In the Simple view, an agent that should only work on attachments needs the "Team resources" pack plus the negative restriction "Search in attachments only". In the backend, `document_access` carries the same tangle: `show_attach_files_control` drives the chat paperclip, `search_attachments_only` (inert without the paperclip) narrows the vector search, hides the library and document pickers, and drops `list_document_tree`. Two positive switches state the same choices directly and remove the special cases.

### Relation to #2837

#2837 (closed 2026-10-03, PR #2838, OpenSpec change `merge-attachments-into-team-resources`) merged the separate "Conversation attachments" card into "Team resources". Its reasoning was that both cards configured the same backend capability, `document_access`. It added "Search in attachments only" below library scoping so the narrower attachments profile stayed easy to select.

- **What this change reverses:** the single Simple card and its negative switch. Members could not tell that an attachments-only agent starts from "Team resources" and is then restricted. Turning the pack on also silently grants corpus search to an agent meant only for attachments. #2837's objection (two cards backed by one capability) is now addressed in the backend instead: each card maps to its own positive `document_access` setting, so no card needs a negative restriction.
- **What this change keeps from #2837 and #2732:** verbatim reading, extraction and summarization stay shared by both document packs. Tabular access stays available for attached CSV and Excel files. Similarity search stays corpus-only. Advanced stays granular and never adds the Simple bundle implicitly. Stored selections are not rewritten on form load or on an unrelated save. Stored library scoping is kept while the member switches sources. Turning a pack off withdraws only the capabilities that no other active pack still grants.

## What Changes

- **`document_access` config (backend):** replace `show_attach_files_control` and `search_attachments_only` with two positive settings, `attachments: bool = True` and `team_documents: bool = True`.
  - `attachments` emits the `attach_files` chat control and lets the search reach the conversation's session scope.
  - `team_documents` lets the search reach the team corpus, enables the library and document scope pickers, makes `bind_libraries` / `library_tag_ids` meaningful, and registers `list_document_tree`.
  - Saving a config with both settings off is rejected; the form deselects the capability instead.
  - Stored and submitted configs that still use the legacy keys are read through a compatibility mapping. The next save writes only the new keys.
- **`DocumentSearchPort.search` (SDK):** two ceilings, `include_attachments` and `include_team_documents`, replace the `attachments_only` keyword. `attachments_only` stays accepted as a deprecated alias (`attachments_only=True` means `include_team_documents=False`), so no caller breaks; its removal date is a reviewer decision (design.md, "Reviewer decisions"). The runtime adapter intersects them with the per-turn RAG scope, so the per-turn control can only narrow what the agent allows. The flags sent to Knowledge Flow and the search ranking stay the same.
- **`rag_scope` chat control:** the capability offers only the per-turn choices its sources allow. For example, "Your documents" (`corpus_only`) is hidden when `team_documents` is off.
- **Simple view:** the single "Team resources" pack is replaced by two independent packs in the "Data and knowledge" section, "Attachments" and "Team documents". The capabilities they share are selected while either pack is on and withdrawn only when both are off. Similarity search belongs to Team documents only. Library binding moves under Team documents. The "Search in attachments only" switch is removed.
- **Advanced view:** the `document_access` card shows the two source switches first, followed by the remaining settings. Scope pickers and library binding are shown only while Team documents is on.
- **Naming:** the user-facing name of `document_access` becomes "Documents" in English and French. The capability id stays `document_access`.
- **Help Center and copy:** English and French Help Center pages, translations, the UX doc, the runtime execution contract and the authoring guide describe the two sources. An English migration note is added.
- **SDK, deprecated keyword (not breaking):** callers of `DocumentSearchPort.search(attachments_only=...)` keep working through the alias. Implementers must accept the two new keywords; in-tree, the only implementer is the fred-runtime adapter plus test fakes, and the only caller is `document_access`.
- **Behavior note:** an agent that had the paperclip turned off (legacy `show_attach_files_control=false`) no longer searches the session scope. Before this change, that agent could not receive attachments through its own composer anyway.

## Capabilities

### New Capabilities

- `document-access-sources`: the `document_access` capability's two source settings, the legacy-config compatibility mapping, and how the sources drive chat controls, registered tools and the search scope ceiling.

### Modified Capabilities

- `agent-capability-packs`: the Simple view's document packs are split into "Attachments" and "Team documents". This capability is not yet under `openspec/specs/`. It is introduced by the implemented but unarchived changes `retire-document-reading-pack` and `merge-attachments-into-team-resources`. Archive both first, then rebase this delta onto the resulting spec (see design.md, "Spec sequencing").

## Impact

- Backend: `libs/capabilities/fred-capability-document-access` (config, manifest fields, chat controls, tools, tests), `libs/fred-sdk` (`DocumentSearchPort.search` signature and port tests), `libs/fred-runtime` (`DocumentSearchAdapter.search`), and test fakes in `libs/capabilities/fred-capability-document-access/tests` and `apps/fred-agents/tests`.
- Frontend: `AgentFormModal/` (`toolPacks.ts`, `toolPackLogic.ts`, `DocumentAccessPackOptions/`, `AgentFormBody.tsx`, Simple view and form tests), `RagScopeControl.tsx` (option filtering), and `locales/{fr,en}/translation.json`.
- Docs: Help Center `features/capabilities.md`, `features/agents.md`, `features/chat.md`, `guides/build-rag-assistant.md` and `troubleshooting/common-problems.md` (fr and en), `docs/swift/ux/COMPONENT-UX.md`, `docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md` §8.15, `docs/swift/capabilities/AUTHORING.md`, `docs/swift/rfc/CAPABILITY-SCOPE-CEILING-RFC.md` §8 open question 2, and one migration note under `docs/swift/ops/migrations/`.
- No database migration, no Knowledge Flow change, and no generated API client change are expected. Chat-control params travel as an untyped dict, and capability config fields are catalog data rather than OpenAPI schema. The implementation verifies that the generated specs do not change.
