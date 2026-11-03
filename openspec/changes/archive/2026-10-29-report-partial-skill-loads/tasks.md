## 1. Runtime guidance and read attribution

- [x] 1.1 Strengthen `NATIVE_SKILLS_SYSTEM_PROMPT` with an explicit 1000-line read example, the 100-line default warning and continuation requirement; verify the real compiled parent/child prompt tests.
- [x] 1.2 Add backward-compatible partial attribution and classify actual native read envelopes without extra I/O or argument rewriting; verify full/partial windows, size and mid-line clipping, unknown coverage, empty/error reads, pins/ReAct defaults and independent concurrent parent/child observations.
- [x] 1.3 Regenerate affected OpenAPI documents and frontend clients from source; verify new typed metadata and legacy payload compatibility through existing stream/history projection tests.

## 2. User-visible disclosure

- [x] 2.1 Preserve the partial flag through existing skill trace parsing and render translated partial labels in the row, shared trace label and accessible name; verify French/English partial, complete and legacy activity cases.
- [x] 2.2 Verify partial activity survives SSE handling and persisted history reload with its original attribution, while continuation/reference reads retain existing count and preview behavior.

## 3. Verification and close-out

- [x] 3.1 Update the existing runtime contract and relevant UX documentation, add a no-action migration note, and verify `make migration-check` against the actual PR base.
- [x] 3.2 Run focused runtime/frontend tests and required root quality checks; apply the full branch audit and independent read-only review plus the performance review for the affected per-tool observation path, recording results and dispositions in the issue/PR.
- [x] 3.3 Reconcile these artifacts with verified behavior, sync the existing capability spec and archive the change using the repository procedures; verify strict validation and the final committed diff exclude the unrelated local model catalog edit.

## Verification

- Runtime: 157 tests pass across `test_platform_skills.py`,
  `test_native_skill_policy.py`, `test_native_skill_read_completeness.py`,
  `test_history.py` and `test_deep_skills_filesystem.py`, with
  `-m 'not integration' --disable-socket --allow-unix-socket`. Compiled Deep
  tests run outside the execution sandbox, which also hangs on an unchanged
  baseline compiled test. One existing LangChain beta warning remains.
- Frontend: 286 tests pass in `traceUtils.test.ts`, `ThoughtTrace.test.tsx` and
  `useChatSse.test.tsx`; `npm run typecheck` passes. Runtime API regeneration
  uses `UV_NO_SYNC=1 make update-runtime-api` from `apps/frontend`.
- Root `make code-quality` passes all modules with `UV_NO_SYNC=1`, a temporary
  uv cache and the installed runtime uv executable supplied as `UV`. This
  reuses module environments without the stale per-module uv/pip bootstrap.
  Raw typing against an empty baseline reports runtime 0 errors/7 existing
  unreachable-code warnings and SDK 0 errors/0 warnings.
- `make migration-check MIGRATION_BASE=origin/swift` validates both branch
  declarations. Change and affected capability strict validation pass;
  standard validation passes all 37 specs. Global strict validation retains
  the unrelated existing placeholder Purpose warning in `frontend-surface-scale`.
- Full branch and focused independent correctness/performance reviews found no
  functional defect. The branch audit's P3 stale slash-label requirement was
  reconciled with the existing UI and independently rechecked. Review base is
  `d76d96ba0f6642871b2191cedb1ecb32df0b0d2a`; production patch commit is
  `ed191f646d11adf91c046edadd59e06918d8ae70`. Detailed coverage and exclusions
  belong in the PR. No new browser/provider, database upgrade or load campaign
  was performed for this slice.
- Both added requirements and all scenarios match the synchronized main spec.
  `git diff --check` passes. The model catalog edit remains outside these commits.

There is no implementation divergence from the approved design. Partial status
describes the individual observed read, without cumulative page tracking.
