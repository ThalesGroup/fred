## Context

See proposal.md and specs/user-ui-preferences/spec.md. Personal theme, mode, sidebar, trace choice and pane widths use `useLocalStorageState`; language uses i18next's `i18nextLng` key; the team and agent sort controls write localStorage directly. `public/theme-boot.js` reads global theme keys before login. The managed workstation can erase all browser storage on restart. `platform_ui_settings` is the administrator's separate default/visibility record. The Control Plane already owns personal product data and `/users/me` routes.

## Goals / Non-Goals

**Goals:**

- Restore durable display choices after browser storage is erased or a user signs in elsewhere.
- Keep one typed record per authenticated subject and avoid changing the shared `users` model.
- Preserve the theme catalog, platform fallback and before-content paint behavior.

**Non-Goals:**

- Store browser-only activity/recovery data: team visit timestamps, unfinished imports, conversation caches, open panels tied to a session or per-conversation todo state.
- Sync security or notice acknowledgements: tool approval grants, upload warning acknowledgements and announcement dismissals keep their existing lifecycle.
- Store theme ZIP/CSS/assets in PostgreSQL or change administrator theme settings.

## Decisions

### Create `users_preferences` in Control Plane

One row per authenticated `user.uid`, with that subject string as the primary key. Use typed columns for `ui_theme_id`, `theme_mode`, `language`, `sidebar_collapsed`, `team_sort_mode`, `agent_sort`, `trace_expanded` and a bounded JSON mapping `pane_widths` for the named resizable panels. Null theme ID means no explicit choice; null language follows navigator language; null trace expansion keeps today's automatic behavior. Defaults for the other fields match today's frontend defaults. The identity row in shared `users` is not guaranteed for every externally authenticated subject, so do not add a foreign key. Delete this row explicitly when deleting a user through Control Plane. One new table and one migration satisfy the requested separation without changing `fred-core`.

### Read and patch self-service preferences

Add authenticated `GET` and `PATCH /control-plane/v1/users/me/preferences`. A read returns typed defaults and `initialized: false` when no row exists. PATCH accepts only known fields; omitted fields remain unchanged, and pane-width entries merge by known key. Validate all fields before writing; backend theme ID syntax matches the platform theme setting, but catalog membership is a frontend concern. The path has no user ID parameter. Partial writes avoid resetting other controls when one setting changes in a second tab. The generated Control Plane client is the sole frontend API binding.

### Hydrate before rendering signed-in content

After OIDC login, obtain the authenticated subject ID, read this user's preference through the generated API client and apply the result to the existing frontend state before mounting application content. If the API fails, a cache keyed by that subject may be used; otherwise use defaults. The static boot script may color only the empty document from public platform settings before identity is known. Theme ID resolution still uses `resolveUiTheme` and retains hidden or absent saved IDs. On a successful read, refresh the scoped cache; changes to a control patch its field and update the cache. Save failures restore the last confirmed value for explicit profile controls and report the error. Browser-local storage may remain as an implementation cache for components, but is not authoritative after hydration.

### Import old browser values once

Before the first profile read, claim the ownerless legacy keys for the first authenticated subject and copy validated values to a snapshot keyed by that subject. When the GET result says no row exists, send that snapshot in one PATCH before application content mounts. Mark that browser's legacy import complete and clear the snapshot only after the server acknowledges the write; a failed read or import remains eligible for that subject to retry while visible controls use user-scoped cache or defaults. Another account cannot consume the pending snapshot. The local keys may continue as a component cache but must not seed another account after the marker is set. Old keys have no account ID, so the initial claim can only assign them to the first authenticated user who loads this browser after upgrade. It is impossible to recover values already erased by workstation policy. The migration note describes this limitation and the UI remains editable if the imported values belong to someone else.

### Keep identifiers and widths bounded

Persist the catalog's stable string theme ID, never a list position or a generated process ID. Archive validation already rejects duplicate custom IDs and IDs colliding with `pebble`, `cobalt` or `cloud`. Document that the same theme keeps its ID across archive updates and frontend restarts. The pane-width map accepts only the known keys used by the wiki rail, import panel and named inline drawers, with positive bounded pixel values; the frontend's viewport clamp remains the final rendering guard.

## Risks / Trade-offs

- [Legacy keys may belong to another person on a shared browser] -> Import only when the database has no row, mark the browser import complete after success, and document that the first import cannot prove ownership.
- [Browser values were cleared before rollout] -> Use defaults; users can choose again and subsequent changes persist centrally.
- [Preference API is unavailable] -> Use the authenticated subject's scoped cache or defaults, keep controls usable, and retry on the next load.
- [Many rapid pane drags] -> Persist the final width when dragging ends rather than sending a request per pointer move.
- [Concurrent updates] -> PATCH only the field changed; the same field uses last-write-wins semantics.

## Migration Plan

Apply the additive `users_preferences` table migration before deploying the new Control Plane and frontend. Existing users have no row and receive defaults or a first-load import. Rollback to older application images leaves the table unused. Dropping it would discard choices saved after rollout. The operator note specifies the sequence, validation, rollback and limitation of already-erased browser data.
