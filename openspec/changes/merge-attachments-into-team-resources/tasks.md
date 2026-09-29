## 1. Pack registry

- [x] 1.1 Remove the standalone attachments card from `toolPacks.ts` and add its granted abilities to Team resources without removing existing resource members; verify the registry and Simple view test show one resource card and its included list has the union.
- [x] 1.2 Update English and French pack copy and remove unused attachments-card translation keys; verify no Simple-view lookup for the retired card remains.

## 2. Pack selection logic

- [x] 2.1 Replace the two-intent resource toggle with one on action that selects all admin-available bundle members and sets document access to corpus plus attachments; verify focused tests cover the full bundle and unavailable members.
- [x] 2.2 Make the off action remove only bundle-owned ids and preserve unrelated capabilities and configs; verify focused tests cover a populated agent and a partial Advanced selection.
- [x] 2.3 Derive the pack's checked state from all available members and both document-access options; verify tests show it on for the full bundle and off for attachment-only, corpus-only, or otherwise partial selections.

## 3. Advanced and legacy behavior

- [x] 3.1 Keep Advanced attachment-only configuration independent of Simple pack activation; verify a focused test shows no corpus search, tabular, or similarity capability is added when attachments are selected in Advanced.
- [x] 3.2 Preserve stored capability selection on form load and unrelated save; verify existing attachment-only and corpus-only agent payload tests keep their selected ids and document-access options.
- [x] 3.3 Verify an existing attachment-only agent's selected capabilities remain active in the combined card's included list while its full-bundle switch reads off; verify a Simple on action selects the full bundle.

## 4. Documentation and validation

- [x] 4.1 Update English and French Help Center guidance and the relevant agent-form UX section to explain the Simple bundle and narrower Advanced choices; verify neither page presents attachments as a separate pack.
- [x] 4.2 Finalize the English migration note for this PR; verify `make migration-check MIGRATION_BASE=origin/swift` passes and the note states that stored agents are not migrated.
- [x] 4.3 Run targeted frontend tests for pack logic, Simple view rendering, and form payloads; verify all pass.
- [x] 4.4 Run root `make code-quality` once before push and the required frontend test suite; record the actual outputs in this change and the PR.
- [x] 4.5 Review the implementation diff, reconcile this change's artifacts with delivered behavior, and run `openspec validate merge-attachments-into-team-resources --strict`; record the prior unarchived delta for post-merge reconciliation in 4.6.
- [ ] 4.6 After merge, reconcile and archive `retire-document-reading-pack` before archiving this change; verify the durable `agent-capability-packs` spec describes one combined Simple pack and independent Advanced settings.

## Verification evidence

- Targeted Vitest run: 3 files, 33 tests passed.
- Frontend `tsc --noEmit`: passed.
- `make migration-check MIGRATION_BASE=origin/swift`: 1 new declaration valid.
- Frontend `make test`: 253 files passed, 1 skipped; 2,962 tests passed, 7 skipped.
- `openspec validate merge-attachments-into-team-resources --strict`: passed.
- Root `make code-quality` with shared `uv` cache in the isolated worktree: passed across all 16 modules, including frontend TypeScript, Prettier, and ESLint.
- Implementation diff reviewed for Simple bundle behavior, independent Advanced settings, retained legacy selections, and product copy.
