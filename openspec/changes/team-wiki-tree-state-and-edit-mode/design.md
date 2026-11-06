## Context

`WikiTree` holds a `collapsed` set in local state (empty = all expanded, lost on unmount). `TeamWikiPage` falls back to the first root page when the URL has no slug. Rename/move goes through a `Dialog` calling the metadata PATCH; content goes through the content PUT with a `base_revision_id` (409 on conflict).

## Goals / Non-Goals

**Goals:** persist tree state locally; move title, parent and delete into edit mode.

**Non-Goals:** cross-device sync, backend changes, changes to the rules page or the review filter.

## Decisions

- **Store expanded ids, not collapsed ones.** Default collapsed then falls out naturally, including for pages created later.
- **One localStorage entry per user** (`team-wiki:tree:<userId>` via `useLocalStorageState`), value `{ [teamId]: { expanded: string[], lastSlug } }`. Per-user because localStorage belongs to the browser; per-team inside because page ids and the last page only make sense within one wiki. State moves from `WikiTree` up to `TeamWikiPage`, which already owns `activeSlug`.
- **Stale ids are ignored, not purged eagerly**: ids not in the current page list are filtered at read time; written state only keeps existing ids.
- **Save order: metadata first, then content.** A duplicate title (the most likely refusal) then fails before anything is written, and edit mode stays open with the draft. Metadata is sent only when title or parent changed. If metadata succeeds and content then hits a 409, the existing conflict flow applies; the retried save no longer sees a metadata diff.
- **Parent search lives in the shared `Select`** as an optional `search` prop (filter field at the top of the menu), and the menu is anchored on the trigger rather than the container so the error slot no longer pushes it down. Only already-packaged atoms are used, so the UI package inputs do not change.
- **Parent select reuses `moveTargets`** and the root option from the current dialog; the dialog and its `renameDialog` i18n keys are deleted.

## Risks / Trade-offs

- [Unbounded growth across many teams] → small payload (ids only); acceptable.
- [Partial save: title applied, content conflict] → visible in the editor title; the conflict banner already explains the content side.
