## Why

The Team Resources table shows only one folder at a time. Moving between distant folders requires repeated breadcrumb navigation, and the surrounding folder structure is not visible while browsing.

## What Changes

- Add an always-visible, resizable folder tree to the left of the corpus table.
- Expand folders in place and load their direct files in bounded pages only when needed.
- A single click on a folder navigates the table to it. Double-clicking the folder name or clicking its chevron expands or collapses it. Double-clicking a file opens the existing document preview. Right-clicking a tree item offers the same available actions as the matching table row.
- Reuse the table folder drop handlers for OS-file drops on tree folders, including the dotted hover target. Keep the table's checkbox selection and existing import panel behavior independent of the tree.
- Keep the current folder highlighted across the full tree row, match the table's body text size, use compact nesting, and scroll horizontally when paths exceed the drawer width.

## Capabilities

### Modified Capabilities

- `team-resource-spaces`: the Team Resources corpus workspace gains a navigable tree drawer.

## Impact

Frontend only: Team Resources workspace, a dedicated tree drawer, localized labels and focused tests. No API or data migration. Local implementation only; tracking issue and PR are deferred until the developer elects to publish this work.
