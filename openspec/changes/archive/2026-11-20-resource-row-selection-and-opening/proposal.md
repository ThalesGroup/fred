# Proposal

## Why

Team Resources currently mixes folder navigation with row selection: clicking a folder name opens it, while clicking elsewhere on a row changes its checkbox. This makes selection and copying names unpredictable. The workspace should use one consistent file-explorer interaction for folders and files.

## What Changes

- A plain click anywhere on a resource row, including its name, selects that row without opening it or previewing it. Ctrl/Cmd-click adds or removes a row from the selection; checkboxes remain usable for independent toggling.
- Double-clicking a folder row opens it. Double-clicking a document row opens its existing preview. Embedded action controls keep their own actions.
- The row, rather than the name text, shows the selected state after a click. Dragging over a name still permits native text selection and copying without changing the selected rows.
- Keyboard access to folder opening and document preview remains available.

## Capabilities

### Modified Capabilities

- `team-resource-spaces`: define selection and activation behavior for the Team Resources corpus table.

## Impact

- Frontend `DocumentWorkspace`, `ResourceExplorer`, `DataTable`, resource-name styling, focused interaction tests and the Resources dashboard design note.
- No backend API, stored data, deployment configuration or permission change.
