## 0. Prerequisites (before any implementation)

- [x] 0.1 Create the GitHub issue for this change, linked to the active milestone, and reference #2837 and #2732. Replace "TBD" in proposal.md. Verify with `gh issue view <n>`.
- [x] 0.2 In this same PR (developer-confirmed), archive `retire-document-reading-pack` (its open task 5.4). Then archive `merge-attachments-into-team-resources` (its open task 4.6: reconcile its one-pack requirements against the first archive). Do this in separate commits that contain no code. Verify that `openspec/specs/agent-capability-packs/spec.md` exists and that `openspec list` no longer shows either change.
- [x] 0.3 Re-check this change's `agent-capability-packs` MODIFIED/REMOVED headers against the archived spec, and copy each modified requirement in full. Verify that `openspec validate split-attachments-and-team-documents --strict` passes without the "Archive would refuse this delta" notice.
  - Done: archive refuses a MODIFIED block that drops a scenario, so the three requirements whose scenarios were renamed after the merge archive are REMOVED and re-ADDED under their original names; "Advanced document choices stay independent" keeps the three merge-era scenarios, rewritten for two packs.

## 1. Backend: document_access config and compatibility

- [x] 1.1 In `fred_capability_document_access/capability.py`, replace `show_attach_files_control` and `search_attachments_only` with `attachments: bool = True` and `team_documents: bool = True`. Extend `_upgrade_legacy_slices` with the legacy mapping (applied only when neither new key is present, legacy keys popped), and add an after-validator that rejects both-off. Verify with table-driven tests in `tests/test_capability.py`: the three legacy shapes, absent `show_attach_files_control`, new keys winning over leftover legacy keys, both-off raising, and `model_dump` holding no legacy key.
- [x] 1.2 Replace the two manifest `FieldSpec`s with `attachments` and `team_documents`, placed first in a `sources` group. Add `ui.visible_when="team_documents"` to `show_library_selection`, `bind_libraries` and `show_document_selection`. Verify with a manifest test that asserts field order, the visibility hints, and that no legacy key remains.
- [x] 1.3 Update `chat_controls()`. `attach_files` is emitted only when `attachments` is on. No `document_scope` control and no bound libraries when `team_documents` is off. `rag_scope` offers all three modes for either document source and preserves a valid `corpus_only` default. Verify by updating `test_chat_controls_each_toggle_hides_its_widget` and the attachments-only tests, and by adding cases for the `rag_scope` options and default fallback.
- [x] 1.4 Update `tools()`. Pass `include_attachments` and `include_team_documents` to the port, and register `list_document_tree` only when `team_documents` is on. Trim the module docstring and comments that describe `search_attachments_only`. Verify by updating `test_attachments_only_pins_search_to_the_session_scope` and `test_attachments_only_drops_the_tree_tool` to the new settings, and by adding a team-documents-only case.

## 2. SDK and runtime: search scope ceilings

- [x] 2.1 In `libs/fred-sdk/fred_sdk/contracts/runtime.py`, add `include_attachments: bool = True, include_team_documents: bool = True` to `DocumentSearchPort.search`, and remove `attachments_only`, its resolver and warning state. Add `options: list[RagScopeName] | None = None` to `RagScopeControlParams` in `contracts/models.py`. Verify that `libs/fred-sdk/tests/test_document_search_port_1906.py` passes with the new keywords.
- [x] 2.2 In `DocumentSearchAdapter.search` (`libs/fred-runtime/fred_runtime/integrations/v2_runtime/adapters.py`), AND the turn scopes from `get_vector_search_scopes` with the two ceilings, and return no hits without calling Knowledge Flow when both are false. Verify with runtime adapter tests for each ceiling combination crossed with `hybrid`, `corpus_only` and `general_only`, asserting the `include_session_scope` / `include_corpus_scope` flags sent.
- [x] 2.3 Update the remaining port fakes: `libs/capabilities/fred-capability-document-access/tests/test_tool_return_convention.py` and `apps/fred-agents/tests/test_test_assistant_document_scenario.py`. Verify that `rg "attachments_only" libs apps` only returns the intentional removed-keyword regression test and legacy stored-config keys.
- [x] 2.4 Confirm that no generated client changes. Run `make generate-openapi` for fred-runtime and control-plane, then `cd apps/frontend && make update-all-apis`. Verify that `git status` shows no change to `runtimeOpenApi.ts` or `controlPlaneOpenApi.ts`, and if one appears, commit the regenerated file as generated.
  - Done: both backend `openapi.json` files regenerated unchanged, so the frontend codegen (not run, to protect the running Vite) has no input change.

## 3. Frontend: Simple packs

- [x] 3.1 In `toolPacks.ts`, replace the `team_resources` pack with `attachments` (document_access, summarize, verbatim, extract, tabular) and `team_documents` (the same plus similarity) in the `data_knowledge` section. Replace `resourceBundle` with `documentSource`, and replace the legacy option-key constants with `DOC_ACCESS_ATTACHMENTS` and `DOC_ACCESS_TEAM_DOCUMENTS`. Verify with a registry test that asserts both cards, their `includes` and their `enablesCapabilityIds`.
- [x] 3.2 Add the pure helper `normalizeDocumentAccessConfig` and apply it in `extractCapabilityConfigValues` (`AgentFormModal.tsx`). Verify with vitest cases mirroring task 1.1's three legacy shapes plus the precedence of new keys, and update `AgentFormModal.test.ts` (lines ~209-213) to the expected normalized values.
- [x] 3.3 Rewrite `toolPackLogic.ts` per design D6. Covered functions: `isPackSelectable`, `derivePackChecked`, and `applyPackToggle` (keep shared members while either pack is on, remove similarity with Team documents, deselect `document_access` and all document members on the last pack off). Delete `applyResourceSearchScope`. Verify by rewriting `toolPackLogic.test.ts` to cover every scenario in `specs/agent-capability-packs` (each pack alone, both, turning off one, turning off the last, unavailable members, unrelated selections preserved, shared-capability-cleared state).
- [x] 3.4 Strip the attachments-only switch from `DocumentAccessPackOptions` and render it only for the `team_documents` pack in `AgentFormBody.tsx`. Verify by updating `DocumentAccessPackOptions.test.tsx` and `SimpleCapabilitiesView.test.tsx` (two cards, library binding only under Team documents).
- [x] 3.5 Prevent saving `document_access` with both sources off, and check the transitive `visible_when` case from design D5 (`bind_libraries` stored true, team documents off). Implemented by deselecting the capability on the last source off, in Advanced (`applyDocumentAccessConfigChange`) and Simple (`applyDocumentPackToggle`), both resetting the sources to on; a save-blocking error was dropped after developer review. Verify with `toolPackLogic.test.ts` and a `CapabilityCard` test for the hidden library picker.

## 4. Frontend: composer and copy

- [x] 4.1 Make `RagScopeControl.tsx` render only `params.options` when present, and make `useComposerSettings` reset a stored `ragScope` that is no longer offered to the control default. Verify with vitest cases for the filtered options and the reset.
- [x] 4.2 Update `locales/{fr,en}/translation.json`:
  - `capability.document_access.name` becomes "Documents".
  - Update the description.
  - Add `fields.attachments` and `fields.team_documents`: fr "Pièces jointes" / "Documents de l'équipe", en "Attachments" / "Team documents".
  - Add pack keys `packs.attachments.*` and `packs.teamDocuments.*`.
  - No blocking-error message (see 3.5).
  - Delete `fields.show_attach_files_control`, `fields.search_attachments_only` and `packs.teamResources`.

  Verify that `rg "teamResources|show_attach_files_control|search_attachments_only" apps/frontend/src` returns nothing.
  - Done: only the `normalizeDocumentAccessConfig` compatibility helper and its tests still name the legacy keys.

## 5. Documentation

- [x] 5.1 Update the fr and en Help Center pages under `apps/frontend/src/rework/features/helpCenter/content/{fr,en}/`, in a non-technical tone using "pièces jointes" / "documents de l'équipe":
  - `features/capabilities.md`: the "Team resources" section becomes "Documents" with two packs; drop the "Search in attachments only" paragraph.
  - `features/agents.md`: the paperclip comes from the Attachments pack.
  - `features/chat.md` and `troubleshooting/common-problems.md`: name the Attachments pack.
  - `guides/build-rag-assistant.md`: turn on Team documents.

  Verify that neither language mentions the retired pack or switch.
- [x] 5.2 Update the docs that describe the retired settings:
  - `docs/swift/ux/COMPONENT-UX.md`: line ~2810 (Outils) and the "`document_access` config/chat parity" section.
  - `docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md`: a dated §8.15 amendment replacing `attachments_only` with the two ceilings.
  - `docs/swift/capabilities/AUTHORING.md`: one sentence on same-version before-validator renames (design D1).

  Verify that `rg "show_attach_files_control|search_attachments_only|attachments_only" docs` only returns the dated history lines.
- [x] 5.3 Trim `docs/swift/rfc/CAPABILITY-SCOPE-CEILING-RFC.md` §8 open question 2: it is settled for document search by this change, and only the summarize and other port ceiling stays open. Verify that the RFC's Status line and open questions reflect what remains.
- [x] 5.4 Add an English migration note from `docs/swift/ops/MIGRATION-NOTE-TEMPLATE.md` at `docs/swift/ops/migrations/split-attachments-and-team-documents.md`. It records the compatibility read, the rewrite on next save, the rollback caveat, the removed SDK keyword, required caller migration and coordinated library updates. Verify with `make migration-check MIGRATION_BASE=origin/swift`.

## 6. Verification and close-out

- [x] 6.1 Run `make code-quality` and `make test` in each touched Python module (`libs/capabilities/fred-capability-document-access`, `libs/capabilities/fred-capability-documents`, `libs/fred-sdk`, `libs/fred-runtime`, `apps/fred-agents`). For the frontend, run `npx tsc --noEmit -p .`, `npx prettier --check` and `npx eslint` on the touched files, focused `npx vitest run` and one full `npx vitest run` (frontend make targets and root `make code-quality` are skipped because they wipe a running Vite's cache). Verify that every run is green, and record the counts in `verification.md`.
- [x] 6.2 Run the `fred-performance-reviewer` skill on the adapter and capability diff, since the per-turn search call site changes. Verify that no finding is left open.
- [ ] 6.3 Manually check on a local stack:
  - a legacy attachments-only agent shows "Attachments" on, has the paperclip, and its search never hits the corpus;
  - a new Team-documents-only agent shows no paperclip and no "Your documents" gap;
  - a re-saved agent stores only the new keys.

  Verify by recording the observations in `verification.md`.
- [ ] 6.4 Apply the three confirmed reviewer decisions in design.md and replace the open questions in the PR description with their answers and verification evidence.
- [ ] 6.5 Reconcile the artifacts with the delivered behavior, run `openspec validate split-attachments-and-team-documents --strict`, and archive once merged. Verify that `openspec/specs/document-access-sources/spec.md` exists and the GitHub issue is closed.

## 7. Reviewer decision follow-up

- [ ] 7.1 Remove the SDK alias, resolver, warning state and fake parameters; verify the removed keyword is rejected.
- [ ] 7.2 Include session attachments in document-only searches, preserve source and turn ceilings, offer document-only mode for either source, and verify all scope combinations and affected consumers.
- [ ] 7.3 Update English/French labels, Help Center and runtime contract; verify document-only answer instructions reach the model.
- [ ] 7.4 Increase every publishable `libs/` package patch version, preserve the npm alpha channel, raise affected SDK/runtime floors and refresh Python/npm consumer locks. Verify release metadata consistency without publishing.
- [ ] 7.5 Run root code quality, affected tests and independent full-branch review against the PR's actual base; record findings and dispositions here or in the PR.
