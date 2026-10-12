## 1. Preparation and contracts

- [ ] 1.1 Obtain developer confirmation of these artifacts and update this independent branch from swift after the metadata PR merges; verify the branch contains that merge and the plan still matches current consumers.
- [ ] 1.2 Add typed paging/filter/sort request and result fields to the existing HTTP, SDK and runtime boundaries; verify legacy calls, invalid argument combinations and empty bounded scopes in contract/adapter tests.

## 2. Authorized store-side selection

- [ ] 2.1 Reuse folder authorization/path resolution without hydrating all item lists or silently capping paged scope; test personal/team/service-agent, descendants and library/document union restrictions.
- [ ] 2.2 Implement the scoped PostgreSQL page query and equivalent SQLite behavior with literal filename/title filtering, permission predicates, stable keyset ordering and unknown-arrival detection; test equal values, unknown dates, wildcard punctuation and unauthorized candidates before page selection.
- [ ] 2.3 Validate cursor shape/version/query fingerprint and fresh authorization on continuation; test malformed/reused cursors, revoked permissions and complete unchanged-corpus traversal.
- [ ] 2.4 Check the actual SQL plan and bounded hydration with a representative large corpus; record results in this task and use one migration if a justified index is needed.

## 3. Rendering and agent integration

- [ ] 3.1 Render a budget-fitting document prefix with hierarchy, unique-document page accounting and no-progress errors; test repeated folder appearances and traversal after budget exhaustion without skipped documents.
- [ ] 3.2 Expose arguments and continuation/unknown-arrival metadata in both document-access tool carriers; test descending limit-one discovery, continuation and vector-search guidance.
- [ ] 3.3 Extend trace parsing/detail for optional page status while hiding cursors and ids; test historical results, current metadata hover, discreet footer and keyboard/narrow-viewport behavior.

## 4. Verification and close-out

- [ ] 4.1 Regenerate Knowledge Flow API output and update the runtime contract, component UX and operator note; verify generated types and documentation match the implemented arguments/results.
- [ ] 4.2 Run relevant focused store/service/adapter/capability/frontend tests and root code-quality once near commit; record raw results and any limitations here and in the PR.
- [ ] 4.3 Obtain independent read-only branch and performance review against the actual swift base, disposition findings, sync specs and archive this change; verify strict validation, then push the implemented draft PR.
