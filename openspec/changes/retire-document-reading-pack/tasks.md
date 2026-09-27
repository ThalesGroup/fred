## 1. Pack registry

- [x] 1.1 Remove the `document_reading` pack from `TOOL_PACK_SECTIONS` in `toolPacks.ts`; verify the "Data and knowledge" section renders three cards and no card offers document reading on its own
- [x] 1.2 Add verbatim reading and exhaustive extraction to the included lists of the "Team resources" and "Conversation attachments" packs; verify each expanded card shows the capabilities listed in the spec's "A pack lists the capabilities it grants" scenarios
- [x] 1.3 Update the file header's shared-capability documentation (truth table and surrounding notes) so it describes the reading pair as resource-pack-owned; verify no comment still describes a standalone reading pack

## 2. Pack activation logic

- [x] 2.1 Extend the resource-pack-owned capability set in `toolPackLogic.ts` with the two reading capability ids; verify toggling a document-access pack no longer leaves a stale reading capability behind
- [x] 2.2 Enable the reading pair on `corpus || attachments` in the resource-state recomputation, matching summarization; verify the four spec scenarios for granting and withdrawing (enable via either pack, survive while one pack remains on, withdrawn when both are off)
- [x] 2.3 Confirm similarity search remains corpus-only; verify an agent with attachments on and team resources off does not get similarity search

## 3. Tests

- [x] 3.1 Remove the retired pack's cases from `toolPackLogic.test.ts`; verify the suite no longer references `document_reading`
- [x] 3.2 Add cases covering the reading pair's shared ownership — granted by either pack, retained while one pack is on, withdrawn when both are off, never added when the platform admin has not enabled the capability; verify `make test` passes in `apps/frontend`
- [x] 3.3 Verify unrelated capabilities (document production packs, capabilities enabled only in the Advanced view) are preserved across a pack toggle

## 4. Copy and documentation

- [x] 4.1 Delete the `packs.documentReading` keys from the French and English translation files; verify no key lookup for that pack remains anywhere in the frontend
- [x] 4.2 Update the Help Center capabilities pages (fr and en) at the three passages naming the retired pack — the pack list, the reading-tools comparison, and the tip box on exhaustive requests; verify the pages describe verbatim reading and extraction as part of the two document-access packs and no longer reference a separate pack
- [x] 4.3 Reconcile the runtime execution contract's note that the Simple view groups the reading pair under one pack (RUNTIME-EXECUTION-CONTRACT.md §8.43); verify the contract matches the shipped behaviour

## 5. Close-out

- [x] 5.1 Run `make code-quality` and `make test` in `apps/frontend`; verify both pass
- [x] 5.2 Run `/code-review` on the diff and address findings; verify no correctness finding remains open
- [x] 5.3 Record verification evidence in this change; verify `openspec validate` passes
- [ ] 5.4 Archive the change once the implementation has merged; verify the capability spec lands under `openspec/specs/agent-capability-packs/`

## Verification evidence

Run 2026-09-18 on `feat/agent-form-default-and-revamp-capabilities`.

- `make code-quality` (apps/frontend) — pass: `tsc --noEmit` clean, Prettier
  clean, ESLint clean.
- `make test` (apps/frontend) — pass: 2463 passed, 9 skipped, 0 failed across
  234 files. `toolPackLogic.test.ts` alone: 25 passed.
- `/code-review` on the working-tree diff — 3 findings, all resolved or
  dispositioned:
  - stale "Phase 2 deferred" claim in RUNTIME-EXECUTION-CONTRACT.md §8.43,
    contradicting §8.44 — fixed in this change (the diff already rewrote that
    paragraph for task 4.3).
  - a new test assertion that read as an availability guard but is not one for
    a document-access pack — comment added stating what it does assert.
- `/code-review` on the branch range `swift...HEAD` before the PR — 3 findings:
  - a spec scenario claiming Advanced-view edits turn a document-access pack
    off, contradicting design.md's own derivation decision — rewritten into two
    accurate scenarios, with a test covering the shared-member case.
  - the §8.43 test sentence still crediting extract with a footer and a config
    cap it lost in Phase 2 — corrected.
  - the "missing capabilities" flag now firing on more teams' team-resources
    card: not a regression in kind (summarize and similarity in that list are
    already ADMIN_GATED), a narrow widening accepted as the consequence of
    listing the reading pair.
  - pre-existing: `withResourceState` writes the pack's capability ids even
    when `document_access` itself is admin-disabled, while the pack's switch
    derives from `document_access` alone — so the switch reads off while ids
    were written, and the Simple view cannot clear them. Present before this
    change (it already affected tabular/summarize/similarity); this change
    widens it to the reading pair. NOT fixed here per the repo's scope
    discipline — tracked separately.

Not covered by automated tests: the rendered pack cards (icons, expanded
"included capabilities" lists) and the Help Center copy were verified by
reading the registry and the Markdown, not by a UI run.
