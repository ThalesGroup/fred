## 1. Preparation and contracts

- [x] 1.1 Obtain developer confirmation of these artifacts and update this independent branch from swift after the metadata PR merges; verify the branch contains that merge and the plan still matches current consumers.
- [x] 1.2 Add typed paging/filter/sort request and result fields to the existing HTTP, SDK and runtime boundaries; verify legacy calls, invalid argument combinations and empty bounded scopes in contract/adapter tests.

## 2. Authorized store-side selection

- [x] 2.1 Reuse folder authorization/path resolution without hydrating all item lists or silently capping paged scope; test personal/team/service-agent, descendants and library/document union restrictions.
- [x] 2.2 Implement the scoped PostgreSQL page query and equivalent SQLite behavior with literal filename/title filtering, permission predicates, stable keyset ordering and unknown-arrival detection; test equal values, unknown dates, wildcard punctuation and unauthorized candidates before page selection.
- [x] 2.3 Validate cursor shape/version/query fingerprint and fresh authorization on continuation; test malformed/reused cursors, revoked permissions and complete unchanged-corpus traversal.
- [x] 2.4 Check the actual SQL plan and bounded hydration with a representative large corpus; record results in this task and use one migration if a justified index is needed.

## 3. Rendering and agent integration

- [x] 3.1 Render a budget-fitting document prefix with hierarchy, unique-document page accounting and no-progress errors; test repeated folder appearances and traversal after budget exhaustion without skipped documents.
- [x] 3.2 Expose arguments and continuation/unknown-arrival metadata in both document-access tool carriers; test descending limit-one discovery, continuation and vector-search guidance.
- [x] 3.3 Extend trace parsing/detail for optional page status while hiding cursors and ids; test historical results, current metadata hover, discreet footer and keyboard/narrow-viewport behavior.

## 4. Verification and close-out

- [x] 4.1 Regenerate Knowledge Flow API output and update the runtime contract, component UX and operator note; verify generated types and documentation match the implemented arguments/results.
- [x] 4.2 Run relevant focused store/service/adapter/capability/frontend tests and root code-quality once near commit; record raw results and any limitations here and in the PR.
- [x] 4.3 Obtain independent read-only branch and performance review against the actual swift base, disposition findings, sync specs and archive this change; verify strict validation, then push the implemented draft PR.

Focused verification so far: selection/service/tag consumers 31 passed; capability 54 passed; runtime adapters 23 passed; frontend parser/detail 18 passed; isolated real PostgreSQL discovery 3 passed. The 10,000-document prepared SQL plan measured approximately 10 ms, top-N heapsort 35 kB and two hydrated candidates. No index migration was justified. Final verification: legacy builder 16 passed and frontend 19 passed, making 147 focused tests across the suites. Native Chromium on the worktree component passed continuation/footer, hover, keyboard focus, Escape, mono font and a 320 px touch viewport without overflow or runtime errors. Final root code-quality passed across every module, reusing installed environments with UV_NO_SYNC=1 and MAKE="make -o dev -o node_modules"; runtime retains five existing baseline warnings. The historical fallback restriction and long-name cursor regression were independently rechecked; the final broad gate includes both. The Knowledge Flow type-check configuration now resolves fred-core from the correct apps/libs layout.

Independent review against swift a7e40a6ff654d86ab783ffe304ecaeb5162e4aeb, HEAD a9f2ed5ddb6a3d5bd04713521bab15e7d725ca4e plus working delta: contract review found lost retry guidance; backend/performance review found quadratic inline descendant selection, the genuine worker authorization seam and out-of-selection folder appearances. All four were corrected and independently rechecked without remaining findings in those responsibilities. Actual OpenFGA revocations/worker identities and concurrent load were not exercised.

Close-out: feature committed as 694e8157c. The subsequent swift release-preparation merge a0f7c4fdf9a4a4f6ef4759474f7f7329f664f11a only changes packaging/release tooling and versions; it changes no reviewed document-discovery source. The final branch targets swift directly, with synced team-resource-spaces requirements and the completed change archived. API generation completed via the frontend update-knowledge-flow-api target using reused installed environments. No full-repository make test, authenticated LLM turn, real OpenFGA revocation or concurrent load campaign was run.

Final cursor-size recheck: a name accepted by the rename API can exceed 8,192 cursor characters while fitting the tree budget. The encoded-position ceiling now accounts for the maximum tree character budget, UTF-8 and Base64 expansion; the generated long-name cursor round-trip regression passed. Selection/service/tag tests now total 32. The root gate passed again after this correction and the updated swift release base.

Repository-wide strict spec validation retains one existing frontend-surface-scale placeholder Purpose warning; this change and the updated team-resource-spaces main spec pass directly.
