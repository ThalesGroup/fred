## 1. Pack registry

- [x] 1.1 Remove the standalone attachments card from `toolPacks.ts` and add its granted abilities to Team resources without removing existing resource members; verify the registry and Simple view test show one resource card and its included list has the union.
- [x] 1.2 Update English and French pack copy and remove unused attachments-card translation keys; verify no Simple-view lookup for the retired card remains.

## 2. Pack selection logic

- [x] 2.1 Replace the two-intent resource toggle with one on action that selects all admin-available bundle members and sets document access to corpus plus attachments; verify focused tests cover the full bundle and unavailable members.
- [x] 2.2 Make the off action remove only bundle-owned ids and preserve unrelated capabilities and configs; verify focused tests cover a populated agent and a partial Advanced selection.
- [x] 2.3 Derive the pack's checked state from the full corpus plus attachments profile; verify tests show it on for the full bundle and off for corpus-only or otherwise partial selections.

- [x] 2.4 Add an attachments-only switch below library scoping in the Simple resource card, wired to the existing document-access setting; verify its visibility and checked state in focused component tests.
- [x] 2.5 Make Simple scope changes update document access and similarity and tabular selection atomically while preserving shared readers, unrelated selections, and stored library scoping; verify both directions with focused tests.
- [x] 2.6 Derive the main pack switch from either complete Simple profile so it remains on while the scope switch is active; verify a complete former attachments-pack selection reads on and an incomplete Advanced selection remains off.

## 3. Advanced and legacy behavior

- [x] 3.1 Keep Advanced attachment-only configuration independent of Simple pack activation; verify a focused test shows no corpus search, tabular, or similarity capability is added when attachments are selected in Advanced.
- [x] 3.2 Preserve stored capability selection on form load and unrelated save; verify existing attachment-only and corpus-only agent payload tests keep their selected ids and document-access options.
- [x] 3.3 Verify an existing attachment-only agent retains its selected capabilities and included-list statuses; a complete former attachments-pack selection reads on with attachments-only scope, while a Simple on action from an incomplete selection selects the full bundle.

- [x] 3.4 Keep Advanced scope edits granular and stored selections unchanged on unrelated saves; verify toggling the Simple option does not alter the independent Advanced behavior.

## 4. Documentation and validation

- [x] 4.1 Update English and French Help Center guidance and the relevant agent-form UX section to explain the Simple bundle and narrower Advanced choices; verify neither page presents attachments as a separate pack.
- [x] 4.2 Finalize the English migration note for this PR; verify `make migration-check MIGRATION_BASE=origin/swift` passes and the note states that stored agents are not migrated.
- [x] 4.3 Run targeted frontend tests for pack logic, Simple view rendering, and form payloads; verify all pass.
- [x] 4.4 Run root `make code-quality` once before push and the required frontend test suite; record the actual outputs in this change and the PR.
- [x] 4.5 Review the implementation diff, reconcile this change's artifacts with delivered behavior, and run `openspec validate merge-attachments-into-team-resources --strict`; record the prior unarchived delta for post-merge reconciliation in 4.6.
- [ ] 4.6 After merge, reconcile and archive `retire-document-reading-pack` before archiving this change; verify the durable `agent-capability-packs` spec describes one combined Simple pack and independent Advanced settings.

- [x] 4.7 Update English and French Help Center, UX, migration guidance, and this change's artifacts for the new scope switch; validate the OpenSpec change and migration declaration.
- [x] 4.8 Run focused and full frontend tests plus root code-quality for this follow-up, review the diff, and record results in the draft PR.

- [x] 4.9 Keep tabular selected when Simple switches to attachments-only while similarity remains off; verify focused selection tests, English and French help, and the migration note against the delivered behavior.

## Verification evidence

Follow-up attachment scope: focused Vitest run passed (4 files, 37 tests); frontend `tsc --noEmit` passed; full frontend `make test` passed (253 files, 1 skipped; 2,964 tests passed, 7 skipped); `make migration-check MIGRATION_BASE=origin/swift` passed; strict OpenSpec validation passed. Root `make code-quality` passed across all 16 modules in the durable isolated worktree. The follow-up diff was reviewed for the two Simple profiles, Advanced independence, legacy selections, disabled form state, and user guidance.


- Targeted Vitest run: 3 files, 33 tests passed.
- Frontend `tsc --noEmit`: passed.
- `make migration-check MIGRATION_BASE=origin/swift`: 1 new declaration valid.
- Frontend `make test`: 253 files passed, 1 skipped; 2,962 tests passed, 7 skipped.
- `openspec validate merge-attachments-into-team-resources --strict`: passed.
- Root `make code-quality` with shared `uv` cache in the isolated worktree: passed across all 16 modules, including frontend TypeScript, Prettier, and ESLint.
- Implementation diff reviewed for Simple bundle behavior, independent Advanced settings, retained legacy selections, and product copy.
