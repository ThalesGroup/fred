## 1. Pack registry and selection logic

- [ ] 1.1 Remove the standalone attachments pack and its two-intent metadata from `toolPacks.ts`; verify the Simple view registry contains one resource pack and the included capability list still reflects team availability.
- [ ] 1.2 Collapse `toolPackLogic.ts` to one resource-pack on/off path, with corpus plus attachment defaults when enabled and removal only of owned ids when disabled; verify focused truth-table tests cover on, off, unavailable capabilities, and preservation of unrelated ids.
- [ ] 1.3 Derive the combined pack's checked state from selected `document_access` alone; verify focused tests show it remains on after an Advanced attachment override and off after document access is deselected.

## 2. Form initialization and persistence

- [ ] 2.1 Apply combined resource defaults when a new template preselects document access, without normalizing an existing agent loaded for edit; verify `AgentFormModal.test.ts` covers a new seeded agent plus legacy corpus-only and attachment-only edit payloads.
- [ ] 2.2 Keep Advanced `document_access` options as the final form state after an explicit change; verify a later unrelated edit preserves the attachment override and re-enabling the Simple pack reapplies the combined defaults.
- [ ] 2.3 Check the create, edit, and duplicate paths that use agent-form payload helpers; verify a targeted test demonstrates no silent legacy normalization outside explicit Simple pack activation.

## 3. Copy and documentation

- [ ] 3.1 Update English and French pack title or description as needed, remove unused attachments-pack translation keys, and verify no Simple-view lookup for the retired pack remains.
- [ ] 3.2 Update English and French Help Center capability guidance and the relevant agent-form UX guidance to explain the combined default, legacy pack reactivation, and Advanced override; verify the copy no longer presents attachments as a separate pack.
- [ ] 3.3 Finalize the English migration note for this PR; verify `make migration-check MIGRATION_BASE=origin/swift` passes and the note states that unrelated edits keep legacy settings.

## 4. Verification and close-out

- [ ] 4.1 Run targeted frontend tests for pack logic, Simple view rendering, and form payloads; verify all pass.
- [ ] 4.2 Run root `make code-quality` once before push and the required frontend test suite; record the actual outputs in this change and the PR.
- [ ] 4.3 Review the implementation diff, reconcile this change's artifacts with delivered behavior, and run `openspec validate merge-attachments-into-team-resources --strict`; verify no conflicting active requirements remain.
- [ ] 4.4 After merge, reconcile and archive the earlier `retire-document-reading-pack` change before archiving this one; verify the durable `agent-capability-packs` spec describes a single resource pack.
