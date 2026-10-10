## 1. Runtime

- [x] 1.1 List the included defaults of a `supports_capabilities=False` template in `available_capabilities` (`_template_capability_entries`). Verify with `test_templates_list_only_included_capabilities_for_definition_that_opts_out`.
- [x] 1.2 Add `resolve_bound_library_ids` and `_instance_bound_library_ids`, pass the result to `FredKnowledgeSearchToolInvoker`. Verify with `tests/test_knowledge_search_bound_libraries.py` and the `document_access` registry tests.
- [x] 1.3 Narrow `knowledge.search` by the bound libraries; an empty intersection returns no hits without searching. Verify with the same test file (no selection, overlap, disjoint, unbound).

## 2. Control plane

- [x] 2.1 Ignore a submitted selection for a template without free selection in `_apply_capability_selection`; update the schema descriptions. Verify with `test_enroll_without_free_selection_configures_included_capabilities` and `test_update_without_free_selection_saves_included_capability_config`.
- [x] 2.2 Regenerate the frontend clients with `make update-control-plane-api update-runtime-api` (only descriptions change in `controlPlaneOpenApi.ts`).

## 3. Frontend

- [x] 3.1 `CapabilityCard` included mode (badge, no switch); Simple and Advanced list included capabilities with their config; neutral line when nothing is included. Verify with `SimpleCapabilitiesView.test.tsx` and `CapabilityCard.test.tsx`.
- [x] 3.2 Submit every included capability and its config (`activeCapabilityIds`). Verify with `AgentFormModal.test.ts`.
- [x] 3.3 Translations, Help Center (en/fr), `COMPONENT-UX.md`.

## 4. Close-out

- [x] 4.1 Contract entries, authoring guide, migration note.
- [x] 4.2 Make `DocumentSearchAdapter.search` and `DocumentTreeAdapter.tree` find nothing for an empty scope (design, D5); state it in the port docstrings. Verify with `test_document_ports_find_nothing_for_an_empty_scope`.
- [ ] 4.3 Manual check on k3d with `mindmap`: an instance bound to one library pins the chat picker and cites only that library.
- [ ] 4.4 Create the GitHub issue, open the PR, archive this change after merge.
