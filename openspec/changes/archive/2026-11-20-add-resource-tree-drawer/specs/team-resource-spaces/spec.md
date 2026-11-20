## ADDED Requirements

### Requirement: Team Resources provides a persistent resource tree

The Team Resources corpus workspace SHALL show an in-scope folder tree beside the main table. The tree SHALL be expanded by default, resizable, and collapsible to a narrow rail with a file-browser icon. Tree text SHALL match the table body size, nested items SHALL use compact indentation, and long paths SHALL be horizontally scrollable. The current folder SHALL remain highlighted across its full row, including on hover.

#### Scenario: Resize and collapse the tree

- **WHEN** the user collapses the tree
- **THEN** its file-browser icon remains available and the table gains the released width
- **WHEN** the user activates the icon
- **THEN** the tree reopens at its previous width
- **WHEN** the user drags the tree's edge
- **THEN** its width changes within the page's bounds and the table remains usable

#### Scenario: Show a deeply nested path

- **WHEN** a nested path or long name exceeds the tree width
- **THEN** the user can scroll horizontally to see the full item
- **WHEN** the user points at the current folder
- **THEN** its entire row remains highlighted

### Requirement: Resource tree follows file browser interactions

A single click on a tree folder SHALL navigate the main table to it without expanding it. Double-clicking the folder or clicking its chevron SHALL expand or collapse its nested children in place. Double-clicking a file SHALL open the existing document preview. Tree navigation SHALL preserve the table's checkbox selection except for the table's existing behavior when changing folders.

#### Scenario: Browse a nested folder

- **WHEN** the user clicks a nested folder once
- **THEN** the main table navigates to that folder and the tree reveals its ancestor path
- **WHEN** the user double-clicks the folder or clicks its chevron
- **THEN** its nested children expand or collapse without navigating again

#### Scenario: Preview a file

- **GIVEN** a file appears under an expanded folder
- **WHEN** the user double-clicks the file
- **THEN** the existing document preview opens for that file

### Requirement: Resource tree reuses file and folder actions

Right-clicking a tree folder or file SHALL offer the actions available from its table row under the same permission and state rules. Dragging OS files over a tree folder SHALL highlight only the pointed drop target, and dropping them SHALL use the existing import flow for that folder.

#### Scenario: Use a context action

- **WHEN** the user right-clicks a folder or file in the tree
- **THEN** the available actions match those of its table row
- **WHEN** the user closes the context menu with Escape
- **THEN** focus returns to the tree item that opened it

#### Scenario: Drop files on a folder

- **WHEN** the user drags OS files over a tree folder
- **THEN** that folder alone shows the drop highlight
- **WHEN** the user drops the files
- **THEN** the existing import flow targets that folder

### Requirement: Resource tree bounds file loading

Expanded folders SHALL load their direct files in bounded pages with a load-more action. A collapsed tree SHALL not initiate folder file loads.

#### Scenario: Open a large folder

- **GIVEN** a folder contains more files than one tree page
- **WHEN** the user expands it
- **THEN** the tree loads only the first page and offers an action to load more

#### Scenario: Refresh while the tree is collapsed

- **WHEN** the resource tags refresh while the tree is collapsed
- **THEN** no tree file loads start until the tree is reopened
