## Why

Priya's original Resources buttons remain gated by Python permissions, while folders already exist in manager. This lot establishes a complete, measurable folder journey on the existing UI. Developer requirements and verified behavior govern it; inherited Swift OpenSpec is evidence to challenge, not authority. Tracking: #3092.

## What Changes

- Keep the existing Resources presentation, two toolbar buttons, breadcrumbs, table and dialogs; bind folder rights and operations to manager.
- Complete creation, browsing, search/sort, rename and recursive deletion of folders/subfolders. Refuse deletion of a subtree containing documents; no document mutation or ingestion.
- Keep permissions on the owning space, with zero folder-specific OpenFGA tuples; bound listing and remove whole-space scans for a small directory.
- Make arc42 the compact architectural account of implemented responsibilities, ownership, authorization, consistency and measured costs. Describe the architecture, not code organization or hypothetical ingestion behavior.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `fred-manager-provisioning`: extend the implemented space-owned resource journey to complete folder management, preserving the original UI.

## Impact

Manager folder contracts/storage queries and generated client; the existing Resources consumers and dialogs; focused correctness, UI and scale checks. No folder ACL model, legacy-data conversion, document workflow, knowledge-base synchronization, folder movement or new explorer. Changes to public pagination and nonempty-folder deletion require explicit acceptance before implementation.
