# Spec Delta

## ADDED Requirements

### Requirement: Team Resources rows support selection and native name copying

The Team Resources corpus table SHALL use row highlighting and its checkbox state to show selected folders and documents. A plain click on a row, including its name, SHALL select that row alone; Ctrl/Cmd-click SHALL toggle that row within the current selection. Checkboxes SHALL continue to toggle independently. Dragging over a folder or document name SHALL allow native text selection and copying without changing row selection.

#### Scenario: Select one row by its name

- **WHEN** a user clicks a folder or document name once without a modifier
- **THEN** only that row is selected and highlighted
- **AND** its name text is not highlighted by the click

#### Scenario: Select several rows

- **GIVEN** one folder or document row is selected
- **WHEN** the user Ctrl/Cmd-clicks another row
- **THEN** both rows are selected and available to the existing bulk actions
- **WHEN** the user Ctrl/Cmd-clicks a selected row
- **THEN** that row is removed from the selection

#### Scenario: Copy a name

- **WHEN** the user drags across a folder or document name
- **THEN** the name text can be selected and copied with the browser's native command
- **AND** the selected rows do not change because of the drag

#### Scenario: Use an embedded control

- **WHEN** the user activates a row checkbox, preview action or menu action
- **THEN** that control performs its existing action without a second row selection change

### Requirement: Team Resources rows open on double-click

The Team Resources corpus table SHALL open a folder on double-click anywhere on its row, including its name, and SHALL open a document's existing preview on double-click anywhere on its row. A single click SHALL only select the row. Keyboard users SHALL retain a way to open folders and document previews.

#### Scenario: Open a folder

- **WHEN** a user double-clicks a folder row or its name
- **THEN** the workspace navigates into that folder

#### Scenario: Preview a document

- **WHEN** a user double-clicks a document row or its name
- **THEN** the existing document preview opens

#### Scenario: Single-click a resource

- **WHEN** a user clicks a folder or document row once
- **THEN** the workspace does not navigate and no preview opens

#### Scenario: Open with the keyboard

- **WHEN** a keyboard user activates the focused folder name with Enter or the existing document preview control
- **THEN** the folder or document preview opens
