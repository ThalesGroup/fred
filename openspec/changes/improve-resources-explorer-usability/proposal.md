# Proposal

## Why

The Resources explorer hides the ends of long names and metadata, while its fixed table columns cannot be widened. The file browser also takes space by default and leaves a tall launcher rail when closed. These behaviors make document identifiers harder to inspect and the table harder to use.

## What Changes

- Reveal each table row's complete displayed name and metadata value on hover without changing selection, copying, or row actions.
- Let users resize the Resources table's labeled columns by dragging with a pointer. Keep header and body aligned; leave other tables unchanged unless they opt in.
- Let users select a bounded, contiguous range of visible Resources rows with Shift-click, including folders and row checkboxes.
- Start the file browser closed for a person without a saved choice. Save only its open/closed state in that person's existing PostgreSQL preferences record and restore it across visits and devices. Keep width and expanded folders on their current browser-local/in-memory paths.
- As the final UI step, replace the closed browser's full-height rail with a small opener in the table toolbar. Keep a close control in the browser header.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `team-resource-spaces`: Define full-value disclosure, adjustable table columns, bounded Shift-click selection, and the new file-browser default and controls.
- `user-ui-preferences`: Add the per-user browser-open choice to the existing self-service preferences record and its documented defaults.

## Impact

- Frontend: Resources table cells, `DataTable` opt-in resizing, `ResourceExplorer` toolbar, `ResourceTreeDrawer`/`InlineDrawer` rail behavior, and focused tests.
- Control Plane: one column on `users_preferences`, preference schemas/store, one Alembic migration, regenerated OpenAPI client, and focused API/store tests.
- Documentation: Resources UX guidance, preference contract, and the required PR migration note. No new service or external dependency.
- Tracking: #3682. Related but separate: #3051 changes default column sizing for all `DataTable` consumers.
