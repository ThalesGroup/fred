# Design

## Context

See [proposal.md](proposal.md). `DocumentWorkspace` supplies the Resources columns to the shared `DataTable` through `ResourceExplorer`. The table uses the same CSS grid track string for separate header and body grids. `ResourceTreeDrawer` currently owns an `open=true` state and uses `InlineDrawer`'s 48px collapsed rail. `InlineDrawer` already stores the tree width in browser storage. The Control Plane already has one `users_preferences` row per authenticated person and a frontend preference store that loads it before the app paints, applies optimistic patches, and rolls back failed saves.

## Goals / Non-Goals

**Goals:** Keep the table's resize behavior opt-in, retain one source of column widths for header and body, and reuse the existing preference record and save path. Keep tree file loading dormant while closed. Preserve focus access when closing the tree.

**Non-Goals:** Change content-based default widths proposed in #3051, save column widths or tree width to PostgreSQL, or save expanded tree branches. No new resource API or table.

## Decisions

1. **Reveal table values in place.** Add the displayed string as the native `title` on the existing truncating name and metadata spans. This follows the shared `DataTable`'s primitive-cell behavior and does not add a tooltip wrapper that could change flex truncation or text selection. Keep the embedded-title and status-specific tooltips as they are.

2. **Opt-in header resize controls.** Add an optional `resizableColumns` mode to `DataTable`, passed only by `ResourceExplorer` for this workspace. Render a handle on each labeled column header, separate from the sort button. Pointer capture changes a width override for that column; Left/Right arrows make fixed increments. Clamp widths to a readable minimum and a finite maximum, and expose the current width through the separator's accessible value. The existing grid track string remains the single source for header and body, with pixel overrides inserted only for adjusted columns. Widths live for the mounted table only. A column without a label, such as status or actions, keeps its supplied track and gets no resize handle.

3. **Extend the existing preference row.** Add one non-null Boolean `resources_tree_open` column with database and model default `false` in a single new Alembic migration. Add it to the self-service read/patch schemas and store mapping, regenerate the Control Plane OpenAPI spec and frontend client, and consume it through `useCurrentUserPreference`/`persistUserPreference`. The browser's previous open state is never imported. The preference is global to the person across Resources workspaces, not keyed by team. Existing row-level locking and per-field PATCH semantics preserve concurrent updates from different pods and other preference fields.

4. **Replace only this rail's collapsed launcher.** Give `InlineDrawer` an opt-in way to occupy zero width and omit its launcher when a rail is closed; current rail consumers retain the existing 48px behavior. Lift the tree's open state to `DocumentWorkspace`, and place a small, labeled file-browser button at the start of `ResourceExplorer`'s toolbar. The button remains mounted so the tree header's close action can return keyboard focus to it before the tree closes. Keep the tree's current header close control and browser-local width resize behavior. Do this visual change after value disclosure, column resizing, and preference persistence.

## Risks / Trade-offs

- **Header/body drift during resizing** -> Build both grids from one updated track string and verify at narrow and wide widths, with and without the optional status column and vertical scrollbar.
- **A title is shown even for a value that fits** -> Match the existing table convention; avoid measurement and per-row observers across pages of documents.
- **A failed preference save could leave the tree looking durable** -> Use the existing optimistic preference store's bounded retry and rollback, and render directly from that store.
- **Closing the rail could lose keyboard focus or leave tree requests running** -> Keep the toolbar opener mounted, return focus there on close, and use the existing `panelOpen` loading guard with the persisted open value.
- **Deployment with a new frontend before the backend migration** -> Ship the migration and generated API in the same release; older rows receive `false`. Rollback of the application can ignore the added column; database downgrade removes it only if a full rollback is explicitly needed.

## Migration Plan

Apply the single Control Plane migration before serving the updated frontend. Existing users start with the file browser closed until they open it. Regenerate OpenAPI clients from the backend source, then deploy the app. A code rollback restores the previous open-by-default rail behavior without data loss; the added preference value remains unused until the new code returns.
