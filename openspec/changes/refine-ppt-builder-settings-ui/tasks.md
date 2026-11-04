# Tasks

## 1. Capability settings table

- [x] 1.1 Move the platform settings gear to a translated rightmost column in `FeaturesPage`, keeping team management in Actions; verify a focused `FeaturesPage` test covers column placement and capabilities with and without a registered panel.

## 2. Agent template return

- [x] 2.1 Add a distinct return-to-platform action to the shared PowerPoint template panel and analysis hook; clear the staged file, template hash, template key and pattern overrides while preserving other settings. Verify focused hook or panel tests cover a saved template, a staged replacement and the default state.
- [x] 2.2 Add English and French labels and any required UX documentation for the reset control; verify both agent form layouts expose the same action and the documented behavior matches the UI.
- [x] 2.3 Verify focused agent form tests show that Save submits a null template hash without a new asset, while closing without Save retains the stored template.

## 3. Integration

- [ ] 3.1 Run the relevant frontend tests and the root `make code-quality` gate once, then review the full branch against `swift`; verify the PR records findings and validation before the change is declared ready.

## Workflow follow-up

- Reconcile the final spec and tasks, sync the delta spec, and archive the change after review.
