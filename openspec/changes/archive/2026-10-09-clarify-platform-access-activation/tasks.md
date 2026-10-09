## 1. Navigation and header

- [x] 1.1 Move the filtering action into PageHeader.actions and remove floating-action styles; verify it remains accessible across top-level and nested tabs with existing guards in focused page tests.
- [x] 1.2 Add Users/Teams sub-tabs under the Whitelist heading using shared navigation and hidden panels; verify import placement, keyboard semantics, retained drafts/selections and team mutations preserving Free state in page tests.

## 2. Activation consent

- [x] 2.1 Extend the existing activation dialog with incomplete-import warning and explicit continue/navigation choices, using existing status and English/French translations; verify continue activates with the reviewed revision, navigation opens Whitelist > Users without mutation, and completed import uses normal confirmation.
- [x] 2.2 Handle loading/failed import status without bypassing consent; verify retry, stale preview, busy state, source guards and unaffected disabling in focused page/dialog tests.

## 3. Verification and close-out

- [x] 3.1 Update the existing UX documentation and migration guide, reconcile and strictly validate this delta, and sync/archive only after implementation verification.
- [x] 3.2 Run focused frontend tests and root make code-quality once for the finished batch; obtain independent read-only review of activation logic and record findings/dispositions in the existing PR. Browser validation remains manual at the user's request.
- [x] 3.3 Commit reviewable navigation and consent blocks separately, push the existing PR, address new quality-bot findings and verify mergeability and all required CI checks on the final head.

Verification: 16 focused PlatformAccessPage tests and root make code-quality passed. Independent bounded review of b9e5cb975 plus the full navigation/consent working delta found no actionable findings; coverage and exclusions are recorded in PR #2966. Browser validation remains manual.

CI: all 140 checks passed on implementation head 3b2cea1474744bb897c148115ea2719c20391d3d. Navigation and consent are isolated in commits 0f7e11a2c and 3b2cea147. All nine quality-bot discussions remain resolved. The final archive-only head is checked again in the PR close-out.
