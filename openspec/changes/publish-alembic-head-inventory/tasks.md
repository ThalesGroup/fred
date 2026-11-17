# Tasks

## 1. Inventory generation

- [x] 1.1 Add a generator that discovers every Alembic tree, reads revision IDs and parents, validates each graph, and writes deterministic head-only Markdown; verify it inventories the current five trees.
- [x] 1.2 Add focused tests for head-only output, a newly added tree, duplicate IDs, missing parents, cycles, and multiple heads; run only the generator's test module during development.

## 2. Release publication

- [x] 2.1 Generate the Alembic head section in both tagged release jobs and include it in each description alongside the existing `migration.md` attachment; verify both workflows use the tagged checkout and the same version argument, with generation failure blocking release creation.
- [x] 2.2 Update the push-release skill to review the generated section before tag approval and confirm both release descriptions after publication; validate the skill and inspect its release walkthrough.
- [x] 2.3 Update the release strategy and add this PR's required migration note; run the migration-note check and verify the documentation distinguishes the head inventory from the operator guide.

## 3. Integration and review

- [ ] 3.1 Run the generator against the repository twice and compare output bytes; run focused tests and workflow syntax validation, then one root code-quality check before push.
- [ ] 3.2 Review the full branch against `swift`, obtain independent read-only review of the generator and CI wiring, fix findings, and open a draft PR with the verified evidence.

## Workflow follow-up

- Reconcile and archive this change after implementation review; release tagging remains governed by the push-release skill's explicit approval gate.
