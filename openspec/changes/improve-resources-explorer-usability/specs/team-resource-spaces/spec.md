# Spec Delta

## ADDED Requirements

### Requirement: Team Resources reveals complete table values

The Team Resources corpus table SHALL reveal the complete displayed value of a document or folder name, size, creation date, or uploader when a pointer hovers its text. Disclosure SHALL leave row selection, native name copying, sorting, and row actions unchanged.

#### Scenario: Inspect a long document name

- **GIVEN** a document name is visually truncated in the table
- **WHEN** the user hovers the name
- **THEN** the complete displayed name is readable without widening the column

#### Scenario: Inspect folder and metadata cells

- **WHEN** the user hovers a folder name or a size, creation date, or uploader value
- **THEN** the complete displayed value is readable, including when the cell is visually truncated
- **AND** clicking or dragging the row retains its existing behavior

### Requirement: Team Resources table columns can be resized

The Team Resources corpus table SHALL let users adjust the width of each labeled data column by dragging with a pointer. Resize boundaries SHALL be visible before hover. Header and body columns SHALL remain aligned during and after resizing; horizontal and vertical scrolling, sorting, selection, and row actions SHALL remain usable. Other tables SHALL retain their existing width behavior unless they enable resizing.

#### Scenario: Drag a column boundary

- **WHEN** the user drags a labeled column's resize control
- **THEN** that column changes width within usable bounds and its header stays aligned with its cells
- **AND** the table can scroll horizontally if its columns no longer fit

#### Scenario: Find a resize boundary

- **WHEN** the Resources table is displayed before the pointer reaches a header
- **THEN** each adjustable column has a subtle gray boundary marker

#### Scenario: Use a table without resize enabled

- **WHEN** another table renders without requesting column resizing
- **THEN** it has no resize controls and retains its existing column widths and interactions

### Requirement: Team Resources supports bounded range selection

The Team Resources corpus table SHALL let a person Shift-click a row or its checkbox to select the inclusive range from the last selected row within the currently rendered page. Files and folders in that range SHALL be selected. A page change or cleared selection SHALL reset the anchor. A Shift-click without an available anchor SHALL select only the clicked row. Ctrl/Cmd-click, ordinary click, text dragging, and row actions SHALL retain their existing behavior.

#### Scenario: Select a range on one page

- **GIVEN** a person has selected a row on the current page
- **WHEN** they Shift-click another row or its checkbox on that page
- **THEN** the contiguous visible rows between those endpoints, including folders, are selected

#### Scenario: Change pages before Shift-click

- **GIVEN** a person selected a row on one page
- **WHEN** they change pages and Shift-click a row
- **THEN** only the clicked row is selected on the new page

## MODIFIED Requirements

### Requirement: Team Resources provides a persistent resource tree

The Team Resources corpus workspace SHALL offer an in-scope folder tree beside the main table. The tree SHALL start closed by default, use a compact table-toolbar opener rather than a full-height collapsed rail, and restore the person's saved open/closed choice across visits and devices. It SHALL remain resizable with browser-local width, compact indentation, horizontally scrollable paths, table-sized text, and a full-row current-folder highlight including on hover.

#### Scenario: Resize and collapse the tree

- **WHEN** the user activates the close control in the tree header
- **THEN** a compact file-browser control remains in the table toolbar and the table gains the released width without a vertical launcher rail
- **WHEN** the user activates that control
- **THEN** the tree reopens at its previous browser-local width
- **WHEN** the user drags the tree's edge
- **THEN** its width changes within the page's bounds and the table remains usable

#### Scenario: Default closed and restore the person's choice

- **GIVEN** a person has no saved file-browser choice
- **WHEN** they open a corpus workspace
- **THEN** the tree is closed
- **WHEN** they open the tree and later visit a corpus workspace on another device
- **THEN** the tree is open for that person

#### Scenario: Show a deeply nested path

- **WHEN** a nested path or long name exceeds the tree width
- **THEN** the user can scroll horizontally to see the full item
- **WHEN** the user points at the current folder
- **THEN** its entire row remains highlighted
