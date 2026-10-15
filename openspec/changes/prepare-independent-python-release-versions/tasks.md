## 1. Track and prepare the change

- [x] 1.1 Create or reuse a tracking GitHub issue, keep work on the dedicated topic branch, and verify the issue and branch identify this change.
- [x] 1.2 Add one `impact: none` migration note for this workflow change and verify it with `make migration-check` against the actual PR base.

## 2. Prepare independent versions

- [x] 2.1 Refactor `scripts/libs_version.py` and the root target to derive an idempotent patch map from the stable code tag for the three shared libraries and explicitly selected changed packages; verify mixed, repeated, and unexpected-version cases with focused script tests.
- [x] 2.2 Update selected internal dependency floors and the runtime/SDK pod chart `appVersion` fields, then verify unchanged capability and `fred-pod` coordinates remain unchanged in a controlled mixed-version fixture.
- [x] 2.3 Support explicit affected-manifest selection and patch increments, including multi-manifest packages and manifest-free packages; verify with focused tests and an old-envelope compatibility test through `resolve_stored_config`.
- [x] 2.4 Synchronize every affected committed `uv.lock` after package changes and verify each locked local distribution matches its project version without unrelated dependency upgrades.

## 3. Validate publication and document the workflow

- [x] 3.1 Refactor `scripts/validate_python_release.py` and the root dry-run/publish targets for per-package versions while preserving dependency order and pre-upload failure; verify mixed-version valid and stale-artifact/floor rejection tests.
- [x] 3.2 Update both shared copies of `push-release/SKILL.md`, `docs/swift/RELEASE-STRATEGY.md`, and `docs/swift/capabilities/AUTHORING.md` with version selection, manifest compatibility, lock synchronization, version-map review, and approval boundaries; verify the documented commands match the implemented targets.
- [x] 3.3 Rehearse a release preparation with one changed multi-manifest capability and one unchanged capability without tags or PyPI upload; verify the version map, lockfile diff, artifact validation, and approval packet.

## 4. Review and close out

- [x] 4.1 Run focused affected tests and one root `make code-quality` near commit, then apply the branch review procedure against the actual target branch and obtain independent read-only review; record findings and verification in the PR.
- [ ] 4.2 Reconcile the OpenSpec artifacts with implementation, sync and archive the change, then push the topic branch and open a draft PR; verify the PR links its issue and includes the migration note.
