# Tasks

## 1. Reveal complete Resources values

- [x] 1.1 Add native hover titles to the existing truncating document name, folder name, size, date, and uploader spans; verify a focused `DocumentWorkspace`/`DocumentNameCell` test reads the complete displayed values without changing selection or copying.
- [x] 1.2 Update the Resources section of `docs/swift/ux/COMPONENT-UX.md` for hover disclosure; verify it matches the rendered cells.

## 2. Resize Resources table columns

- [x] 2.1 Add opt-in pointer drag column resize controls to shared `DataTable`, pass the option through `ResourceExplorer`, and enable it for `DocumentWorkspace`; verify focused table tests cover header/body track alignment, bounds, sort isolation, and no handles in tables without the option.
- [ ] 2.2 Verify the Resources table stays usable with optional status cells and horizontal/vertical scrolling at narrow widths, and document the interaction in `docs/swift/ux/COMPONENT-UX.md`.
- [x] 2.3 Add opt-in Shift-click range selection for visible Resources rows and checkboxes, including folders; verify page bounds, anchor reset, and existing Ctrl/Cmd and text-drag behavior with focused tests.

## 3. Persist file-browser visibility by person

- [x] 3.1 Add `resources_tree_open` with default `false` to the existing `users_preferences` table in one Control Plane migration, plus read/patch schema and store support; verify focused preference tests cover defaults, partial updates, isolation, and account deletion.
- [x] 3.2 Regenerate the Control Plane OpenAPI spec and frontend client from the backend source; verify generated types expose the field and no generated file was hand-edited.
- [x] 3.3 Drive the tree's open state from the existing frontend preference store and save changes through its retry/rollback path; verify focused frontend tests cover default closed, saved open, failed save rollback, and no file loads while closed.
- [x] 3.4 Update the preference contract and the required PR migration note for the one-column change; verify both describe the default and deployment order.

## 4. Replace the collapsed rail last

- [x] 4.1 Add an opt-in rail mode that occupies no width when closed, add the small file-browser button to the Resources toolbar, and return focus to it from the tree header's close control; verify focused interaction tests and that other `InlineDrawer` rails retain their current behavior.
- [ ] 4.2 Update the resource-tree section of `docs/swift/ux/COMPONENT-UX.md` and verify the compact opener, open tree, keyboard access, and narrow layout in the UI.

## 5. Integration and review

- [ ] 5.1 Run the focused frontend and Control Plane suites, the single root `make code-quality` pass, and the repository branch audit; verify every finding is resolved or recorded with an explicit disposition.
- [x] 5.2 Obtain an independent read-only review of the complete diff, reconcile the OpenSpec artifacts with the result, and record verification and exclusions in the draft PR for #3682.

## Workflow follow-up

- Sync and archive the change after implementation and required review, then open the draft PR against `swift`.
