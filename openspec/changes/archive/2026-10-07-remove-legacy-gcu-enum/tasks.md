## 1. Retire the compatibility surface

- [x] 1.1 Delete the enum, its imports and public reexports; use `str` in both user-store signatures and persist it directly. Verify Python sources have no remaining enum references.
- [x] 1.2 Replace the existing store test's enum input with `"v1"`, preserving the existing assertions and concurrency coverage; verify the offline test passes.
- [x] 1.3 Add the operator migration note for the retired Python API without editing published notes or historical migrations; verify `migration-check` passes.

## 2. Verify and publish

- [x] 2.1 Run the offline user-store, GCU acceptance and admission tests; check the exported module surfaces and affected consumers.
- [x] 2.2 Run `make code-quality` once from the worktree root, the modified package's offline suite and raw basedpyright; validate the migration note and OpenSpec change.
- [x] 2.3 Complete author and independent read-only reviews against `origin/swift`; verify no unresolved findings and retain reviewed base/head and verification evidence for the PR.
- [x] 2.4 Reconcile the artifacts with the final implementation and deployment impacts; verify strict OpenSpec validation.

Archive, commit, push and update the draft PR after implementation tasks are complete. Record review and verification evidence in that PR.
