## 1. Retire the compatibility surface

- [ ] 1.1 Delete the enum, its imports and public reexports; use `str` in both user-store signatures and persist it directly. Verify Python sources have no remaining enum references.
- [ ] 1.2 Replace the existing store test's enum input with `"v1"`, preserving the existing assertions and concurrency coverage; verify the offline test passes.
- [ ] 1.3 Add the operator migration note for the retired Python API without editing published notes or historical migrations; verify `migration-check` passes.

## 2. Verify and publish

- [ ] 2.1 Run the offline user-store, GCU acceptance and admission tests; check the exported module surfaces and affected consumers.
- [ ] 2.2 Run `make code-quality` once from the worktree root, the modified package's offline suite and raw basedpyright; validate the migration note and OpenSpec change.
- [ ] 2.3 Complete author and independent read-only reviews against `origin/swift`; record reviewed base/head, findings, dispositions and verification in the PR.
- [ ] 2.4 Reconcile the artifacts, sync and archive the change, commit the completed block, push and update the draft PR linked to issue #2995.
