## Why

The team wiki tree opens fully expanded and forgets its state as soon as the user leaves, so a deep wiki is noisy on arrival and has to be re-navigated on every visit. Title, location and delete live in separate icons and a dialog next to the article, apart from the edit mode where users actually change a page. GitHub issue #3489.

## What Changes

- The tree starts fully collapsed on a first visit.
- Expanded pages and the last opened page are remembered in browser localStorage, per user and per team.
- Opening the wiki without a page in the URL reopens the last viewed page (or the first page if it no longer exists).
- The ancestors of the open page are expanded so it is always visible in the tree.
- Edit mode carries the title field, the parent page select and a delete icon button (error color, "Delete page" tooltip, existing confirmation).
- Reading view loses the "Title and location" and "Delete" icons; the "Title and location" dialog is removed.
- The rules page is unchanged: fixed title, no parent, no delete.

## Capabilities

### New Capabilities
- `team-wiki`: team wiki browsing and page editing as seen in the frontend (tree state, edit mode).

### Modified Capabilities

## Impact

Frontend only: `apps/frontend/src/rework/components/pages/TeamWikiPage/` (TeamWikiPage, WikiTree, WikiArticle, WikiEditor and their tests) and fr/en `rework.wiki.*` translations. No backend, API or contract change; existing content and metadata endpoints are reused.
