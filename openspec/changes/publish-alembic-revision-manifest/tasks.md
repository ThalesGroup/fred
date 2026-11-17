# Tasks

## 1. Inventory generation

- [x] 1.1 Add a generator that discovers every Alembic tree, reads all revision metadata, validates each graph, and writes deterministic Markdown; verify it inventories the current five trees and identifies their heads.
- [x] 1.2 Add focused tests for stable ordering, a newly added tree, duplicate IDs, missing parents, cycles, and multiple heads; run only the generator's test module during development.

## 2. Release publication

- [x] 2.1 Generate `alembic-revisions.md` in both tagged release jobs and attach it alongside `migration.md`; verify both workflows use the tagged checkout and the same version argument, with a missing inventory blocking release creation.
- [x] 2.2 Update the push-release skill to review the generated inventory before tag approval and confirm both attached assets after publication; validate the skill and inspect its release walkthrough.
- [x] 2.3 Update the release strategy and add this PR's required migration note; run the migration-note check and verify the documentation distinguishes the revision inventory from the operator guide.

## 3. Integration and review

- [ ] 3.1 Run the generator against the repository twice and compare output bytes; run focused tests and workflow syntax validation, then one root code-quality check before push.
- [ ] 3.2 Review the full branch against `swift`, obtain independent read-only review of the generator and CI wiring, fix findings, and open a draft PR with the verified evidence.

## Workflow follow-up

- Reconcile and archive this change after implementation review; release tagging remains governed by the push-release skill's explicit approval gate.
