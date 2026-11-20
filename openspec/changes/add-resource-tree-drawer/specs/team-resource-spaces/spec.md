## ADDED Requirements

### Requirement: Team Resources offers a navigable tree drawer

The Team Resources corpus workspace SHALL offer an always-visible, resizable left drawer. The drawer SHALL show the same in-scope folders as the main table, nested by path. A single click on a folder name SHALL navigate the table to it. A single click on its name SHALL NOT expand it. Double-clicking its name or clicking its chevron SHALL expand or collapse its nested children in place. Double-clicking a file SHALL open the existing document preview. Right-clicking a folder or file SHALL offer the actions available from its table row, subject to the same permission and state rules. Dragging OS files over a tree folder SHALL highlight that folder as a drop target and dropping them SHALL use the existing import flow for that folder. The current folder SHALL remain highlighted across the whole tree row on hover. Tree item text SHALL match the table body text size, nested items SHALL use compact indentation, and the drawer SHALL scroll horizontally when its content exceeds its width. Tree navigation SHALL NOT alter the table's checkbox selection except for the table's existing behavior when changing folders.

#### Scenario: Browse a nested folder

- **WHEN** a user expands a folder in the drawer
- **THEN** its direct child folders and first bounded page of direct files appear
- **WHEN** the user selects a nested folder
- **THEN** the main table navigates to that folder and the drawer reveals its ancestor path

#### Scenario: Preview a file

- **GIVEN** a file appears under an expanded folder
- **WHEN** the user double-clicks the file
- **THEN** the existing document preview opens for that file

#### Scenario: Large folder

- **GIVEN** a folder has more files than one drawer page
- **WHEN** the user expands it
- **THEN** the drawer loads only the first page and offers an action to load more

#### Scenario: Resize and scroll the drawer

- **WHEN** the user drags the drawer's edge
- **THEN** its width changes within the page's bounds and the table remains usable
- **WHEN** a deeply nested path or long name exceeds the drawer width
- **THEN** the user can scroll horizontally to see the full item while the tree remains visible
- **WHEN** the user points at the current folder after navigating to it
- **THEN** the entire folder row remains highlighted
