## Context

DocumentWorkspace already builds the authorized tag tree and loads a paginated folder view. The existing preview command opens DocumentPreviewDrawer. TeamWikiPage already uses usePaneResize for a left rail.

## Decisions

- Render the tree beside ResourceExplorer inside DocumentWorkspace so folder navigation and file preview reuse its current callbacks. Do not introduce another route or backend endpoint.
- Reuse usePaneResize with a persisted width. Keep the tree visible while the import panel remains on the right.
- Give the current folder one full-row selected state, even on hover. Match the table body font, reduce each nesting step to 8px, and let long names and deep paths widen the tree content so the drawer scrolls horizontally.
- Reuse the table's already-loaded name-ordered pages for expanded folders when available. Otherwise fetch direct document pages through the existing browse-by-tag API, 50 at a time. Do not prefetch the corpus or traverse documents for closed branches. Show a load-more control when the server reports additional files.
- Use the table row action definitions and handlers for the tree context menu, with the clicked file's owning tag rather than the table's current tag. Keep tree file highlighting local to the drawer. It does not change table checkbox selection or bulk actions. Opening a folder through the table or breadcrumb reveals its ancestors in the tree without expanding the current folder itself. After renaming or deleting an ancestor, reconcile the current path and back history. Patch tree-only file metadata after successful search-visibility or label changes.
- Clear the drawer's loaded file pages on a new tag snapshot, then reload open branches. Ignore stale in-flight responses.

## Verification

Focused component tests cover expansion, bounded paging, folder navigation and file preview. Run the affected frontend type check and formatting check; manually inspect layout and resizing at the local frontend viewport if available.
