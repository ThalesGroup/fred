## 0. Prerequisites (before any implementation)

- [x] 0.1 Create the GitHub issue for this change, linked to the active milestone, and reference #2837 and #2732. Replace "TBD" in proposal.md. Verify with `gh issue view <n>`.
- [ ] 0.2 In this same PR (developer-confirmed), archive `retire-document-reading-pack` (its open task 5.4). Then archive `merge-attachments-into-team-resources` (its open task 4.6: reconcile its one-pack requirements against the first archive). Do this in separate commits that contain no code. Verify that `openspec/specs/agent-capability-packs/spec.md` exists and that `openspec list` no longer shows either change.
- [ ] 0.3 Re-check this change's `agent-capability-packs` MODIFIED/REMOVED headers against the archived spec, and copy each modified requirement in full. Verify that `openspec validate split-attachments-and-team-documents --strict` passes without the "Archive would refuse this delta" notice.

## 1. Backend: document_access config and compatibility

- [ ] 1.1 In `fred_capability_document_access/capability.py`, replace `show_attach_files_control` and `search_attachments_only` with `attachments: bool = True` and `team_documents: bool = True`. Extend `_upgrade_legacy_slices` with the legacy mapping (applied only when neither new key is present, legacy keys popped), and add an after-validator that rejects both-off. Verify with table-driven tests in `tests/test_capability.py`: the three legacy shapes, absent `show_attach_files_control`, new keys winning over leftover legacy keys, both-off raising, and `model_dump` holding no legacy key.
- [ ] 1.2 Replace the two manifest `FieldSpec`s with `attachments` and `team_documents`, placed first in a `sources` group. Add `ui.visible_when="team_documents"` to `show_library_selection`, `bind_libraries` and `show_document_selection`. Verify with a manifest test that asserts field order, the visibility hints, and that no legacy key remains.
- [ ] 1.3 Update `chat_controls()`. `attach_files` is emitted only when `attachments` is on. No `document_scope` control and no bound libraries when `team_documents` is off. `rag_scope` gets `options` without `corpus_only` when `team_documents` is off, and an unoffered `default_rag_scope` falls back to `hybrid`. Verify by updating `test_chat_controls_each_toggle_hides_its_widget` and the attachments-only tests, and by adding cases for the `rag_scope` options and default fallback.
- [ ] 1.4 Update `tools()`. Pass `include_attachments` and `include_team_documents` to the port, and register `list_document_tree` only when `team_documents` is on. Trim the module docstring and comments that describe `search_attachments_only`. Verify by updating `test_attachments_only_pins_search_to_the_session_scope` and `test_attachments_only_drops_the_tree_tool` to the new settings, and by adding a team-documents-only case.

## 2. SDK and runtime: search scope ceilings

- [ ] 2.1 In `libs/fred-sdk/fred_sdk/contracts/runtime.py`, add `include_attachments: bool = True, include_team_documents: bool = True` to `DocumentSearchPort.search`, and keep `attachments_only` as a deprecated alias (maps to `include_team_documents=False`, warns once per process). Add `options: list[RagScopeName] | None = None` to `RagScopeControlParams` in `contracts/models.py`. Verify that `libs/fred-sdk/tests/test_document_search_port_1906.py` passes with the new keywords.
- [ ] 2.2 In `DocumentSearchAdapter.search` (`libs/fred-runtime/fred_runtime/integrations/v2_runtime/adapters.py`), AND the turn scopes from `get_vector_search_scopes` with the two ceilings, and return no hits without calling Knowledge Flow when both are false. Verify with runtime adapter tests for each ceiling combination crossed with `hybrid`, `corpus_only` and `general_only`, asserting the `include_session_scope` / `include_corpus_scope` flags sent.
- [ ] 2.3 Update the remaining port fakes: `libs/capabilities/fred-capability-document-access/tests/test_tool_return_convention.py` and `apps/fred-agents/tests/test_test_assistant_document_scenario.py`. Verify that `rg "attachments_only" libs apps` only returns the SDK alias, its test and the adapter's alias handling.
- [ ] 2.4 Confirm that no generated client changes. Run `make generate-openapi` for fred-runtime and control-plane, then `cd apps/frontend && make update-all-apis`. Verify that `git status` shows no change to `runtimeOpenApi.ts` or `controlPlaneOpenApi.ts`, and if one appears, commit the regenerated file as generated.

## 3. Frontend: Simple packs

- [ ] 3.1 In `toolPacks.ts`, replace the `team_resources` pack with `attachments` (document_access, summarize, verbatim, extract, tabular) and `team_documents` (the same plus similarity) in the `data_knowledge` section. Replace `resourceBundle` with `documentSource`, and replace the legacy option-key constants with `DOC_ACCESS_ATTACHMENTS` and `DOC_ACCESS_TEAM_DOCUMENTS`. Verify with a registry test that asserts both cards, their `includes` and their `enablesCapabilityIds`.
- [ ] 3.2 Add the pure helper `normalizeDocumentAccessConfig` and apply it in `extractCapabilityConfigValues` (`AgentFormModal.tsx`). Verify with vitest cases mirroring task 1.1's three legacy shapes plus the precedence of new keys, and update `AgentFormModal.test.ts` (lines ~209-213) to the expected normalized values.
- [ ] 3.3 Rewrite `toolPackLogic.ts` per design D6. Covered functions: `isPackSelectable`, `derivePackChecked`, and `applyPackToggle` (keep shared members while either pack is on, remove similarity with Team documents, deselect `document_access` and all document members on the last pack off). Delete `applyResourceSearchScope`. Verify by rewriting `toolPackLogic.test.ts` to cover every scenario in `specs/agent-capability-packs` (each pack alone, both, turning off one, turning off the last, unavailable members, unrelated selections preserved, shared-capability-cleared state).
- [ ] 3.4 Strip the attachments-only switch from `DocumentAccessPackOptions` and render it only for the `team_documents` pack in `AgentFormBody.tsx`. Verify by updating `DocumentAccessPackOptions.test.tsx` and `SimpleCapabilitiesView.test.tsx` (two cards, library binding only under Team documents).
- [ ] 3.5 Raise a save-blocking error through `capabilityBlockingErrors` when `document_access` is selected with both sources off, and check the transitive `visible_when` case from design D5 (`bind_libraries` stored true, team documents off). Verify with a vitest test on the form that asserts Save is blocked, plus a `CapabilityCard` test for the hidden library picker.

## 4. Frontend: composer and copy

- [ ] 4.1 Make `RagScopeControl.tsx` render only `params.options` when present, and make `useComposerSettings` reset a stored `ragScope` that is no longer offered to the control default. Verify with vitest cases for the filtered options and the reset.
- [ ] 4.2 Update `locales/{fr,en}/translation.json`:
  - `capability.document_access.name` becomes "Documents".
  - Update the description.
  - Add `fields.attachments` and `fields.team_documents`: fr "Pièces jointes" / "Documents de l'équipe", en "Attachments" / "Team documents".
  - Add pack keys `packs.attachments.*` and `packs.teamDocuments.*`.
  - Add the blocking-error message.
  - Delete `fields.show_attach_files_control`, `fields.search_attachments_only` and `packs.teamResources`.

  Verify that `rg "teamResources|show_attach_files_control|search_attachments_only" apps/frontend/src` returns nothing.

## 5. Documentation

- [ ] 5.1 Update the fr and en Help Center pages under `apps/frontend/src/rework/features/helpCenter/content/{fr,en}/`, in a non-technical tone using "pièces jointes" / "documents de l'équipe":
  - `features/capabilities.md`: the "Team resources" section becomes "Documents" with two packs; drop the "Search in attachments only" paragraph.
  - `features/agents.md`: the paperclip comes from the Attachments pack.
  - `features/chat.md` and `troubleshooting/common-problems.md`: name the Attachments pack.
  - `guides/build-rag-assistant.md`: turn on Team documents.

  Verify that neither language mentions the retired pack or switch.
- [ ] 5.2 Update the docs that describe the retired settings:
  - `docs/swift/ux/COMPONENT-UX.md`: line ~2810 (Outils) and the "`document_access` config/chat parity" section.
  - `docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md`: a dated §8.15 amendment replacing `attachments_only` with the two ceilings.
  - `docs/swift/capabilities/AUTHORING.md`: one sentence on same-version before-validator renames (design D1).

  Verify that `rg "show_attach_files_control|search_attachments_only|attachments_only" docs` only returns the dated history lines.
- [ ] 5.3 Trim `docs/swift/rfc/CAPABILITY-SCOPE-CEILING-RFC.md` §8 open question 2: it is settled for document search by this change, and only the summarize and other port ceiling stays open. Verify that the RFC's Status line and open questions reflect what remains.
- [ ] 5.4 Add an English migration note from `docs/swift/ops/MIGRATION-NOTE-TEMPLATE.md` at `docs/swift/ops/migrations/split-attachments-and-team-documents.md`. It records the compatibility read, the rewrite on next save, the rollback caveat, the deprecated SDK `attachments_only` alias, and impact `none` (patch). Verify with `make migration-check MIGRATION_BASE=origin/swift`.

## 6. Verification and close-out

- [ ] 6.1 Run `make code-quality` from the repository root once, then `make test` in `libs/capabilities/fred-capability-document-access`, `libs/fred-sdk`, `libs/fred-runtime`, `apps/fred-agents` and `apps/frontend`. Warn about and restart a running Vite. Verify that every run is green, and record the counts in `verification.md`.
- [ ] 6.2 Run the `fred-performance-reviewer` skill on the adapter and capability diff, since the per-turn search call site changes. Verify that no finding is left open.
- [ ] 6.3 Manually check on a local stack:
  - a legacy attachments-only agent shows "Attachments" on, has the paperclip, and its search never hits the corpus;
  - a new Team-documents-only agent shows no paperclip and no "Your documents" gap;
  - a re-saved agent stores only the new keys.

  Verify by recording the observations in `verification.md`.
- [ ] 6.4 In the PR description, ask the reviewer (expected: dimitri-tombroff) the two questions in design.md "Reviewer decisions" (alias removal timing; whether "Your documents" includes attachments), with the developer's opinion on each. Apply the decisions before merge and record them in design.md. Verify that design.md holds no undecided point.
- [ ] 6.5 Reconcile the artifacts with the delivered behavior, run `openspec validate split-attachments-and-team-documents --strict`, and archive once merged. Verify that `openspec/specs/document-access-sources/spec.md` exists and the GitHub issue is closed.
