# Design

## Context

See proposal.md. `DocumentWorkspace` owns the selected keys, folder navigation and document preview command. `ResourceExplorer` forwards row callbacks to the shared `DataTable`. `DataTable` already distinguishes row background from embedded controls, and its checkboxes supply keyboard selection. The folder name is currently a button with a single-click navigation handler; document names are plain text in `DocumentNameCell`.

## Goals / Non-Goals

**Goals:** Keep the visible checkbox state and bulk-action selection in one controlled set, and route double-click activation to the existing navigation and preview operations.

**Non-Goals:** Add a new preview route, clipboard action or server request.

## Decisions

- Add an opt-in selection mode to `DataTable`: a plain row click replaces the controlled selection and Ctrl/Cmd-click toggles a key. Existing consumers retain their current behavior. Keep checkbox toggling independent.
- Treat the folder name button as part of its row for pointer clicks and double-clicks, while Enter on that focused button continues to navigate. Other embedded controls remain isolated from row events. This preserves a keyboard opening path without adding a new control.
- Ignore row selection when a pointer gesture begins on selectable name text and ends with a non-collapsed text selection. Track the pointer-down target so a later click on the row background can still select that row.
- Use the existing `commands.preview` for document double-clicks and the existing `navigateTo` for folders. Keep row keys and selection scoped to the currently visible page as before.
- Override the button reset's `user-select: none` on the folder name button and keep text selection on the document name. The selected row tint remains the item-selection indicator.
- Keep the ResourceExplorer toolbar on one line with stable breadcrumb/action widths. The action side can scroll horizontally with a visible scrollbar so changing selection cannot shift rows between clicks.

## Risks / Trade-offs

- Text dragging and double-clicking both interact with native selection. Focused event tests cover the intended dispatch paths; manual browser verification is still needed because the local browser automation rejected the test URL.
- A second click in a double-click must not reverse a Ctrl/Cmd selection. Ignore the second click for row selection and let the double-click callback activate the resource.

## Migration Plan

Deploy the frontend normally. The existing preview, folder and bulk-action APIs remain unchanged. Reverting this PR restores the previous interactions.
