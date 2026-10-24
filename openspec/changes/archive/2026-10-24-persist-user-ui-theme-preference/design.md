## Context

See proposal.md and specs/user-ui-preferences/spec.md. Before this change, personal display controls use browser storage for runtime state. After this change, database values are loaded into account-specific in-memory state. Pane widths retain browser storage. `public/theme-boot.js` may read the public platform catalog and settings but not personal theme or mode keys. The managed workstation can erase browser storage on restart. `platform_ui_settings` is the administrator's separate default/visibility record. The Control Plane already owns personal product data and `/users/me` routes.

## Goals / Non-Goals

**Goals:**

- Restore durable display choices after browser storage is erased or a user signs in elsewhere.
- Keep one typed record per authenticated subject and avoid changing the shared `users` model.
- Preserve the theme catalog, platform fallback and before-content paint behavior.

**Non-Goals:**

- Store browser-only activity/recovery data: team visit timestamps, conversation caches, open panels tied to a session or per-conversation todo state.
- Sync security or notice acknowledgements: tool approval grants, upload warning acknowledgements and announcement dismissals keep their existing lifecycle.
- Store theme ZIP/CSS/assets in PostgreSQL or change administrator theme settings.

## Decisions

### Create `users_preferences` in Control Plane

One row per authenticated `user.uid`, with that subject string as the primary key. Use typed columns for `ui_theme_id`, `theme_mode`, `language`, `sidebar_collapsed`, `team_sort_mode`, `agent_sort` and `trace_expanded`. Resizable pane widths remain in browser localStorage and are absent from the database contract. Null theme ID means no explicit choice; null language follows navigator language; null trace expansion keeps today's automatic behavior. Defaults for the other fields match today's frontend defaults. The identity row in shared `users` is not guaranteed for every externally authenticated subject, so do not add a foreign key. Delete this row explicitly when deleting a user through Control Plane. One new table and one migration satisfy the requested separation without changing `fred-core`.

### Read and patch self-service preferences

Add authenticated `GET` and `PATCH /control-plane/v1/users/me/preferences`. A read returns typed defaults and `initialized: false` when no row exists. PATCH accepts only known fields; omitted fields remain unchanged. Validate all fields before writing; backend theme ID syntax matches the platform theme setting, but catalog membership is a frontend concern. The path has no user ID parameter. Partial writes avoid resetting other controls when one setting changes in a second tab. The generated Control Plane client is the sole frontend API binding.

### Hydrate before rendering signed-in content

After OIDC login, obtain the authenticated subject ID, read this user's preference through the generated API client and apply the result to in-memory frontend controls before mounting application content. An absent row or failed read applies documented defaults; the frontend never reads personal browser keys to seed or recover database preferences. The static boot script uses only public platform settings and the OS color mode before identity is known. Theme ID resolution still uses `resolveUiTheme` and retains hidden or absent saved IDs. Changes to a control patch its field. Convenience controls retry transient failures once in write order, then restore the last confirmed database value if the save still fails. Explicit profile controls report failed saves. The Help Center language switch remains usable during a preference API outage and warns when its route-local choice was not saved. Personal controls do not read or write localStorage; separate tabs cannot exchange one account's display choices through origin-wide storage events.

### Start existing users from database defaults

The migration creates an empty table. A GET without a row returns typed defaults and `initialized: false`; it does not trigger a PATCH. The frontend applies those defaults even when a browser still contains personal choices from an older deployment. A failed GET also applies defaults for that load and retries on the next load. No one-time import marker, pending snapshot or per-user browser fallback is needed.

### Keep theme identifiers stable and widths local

Persist the catalog's stable string theme ID, never a list position or a generated process ID. Archive validation already rejects duplicate custom IDs and IDs colliding with `pebble`, `cobalt` or `cloud`. Document that the same theme keeps its ID across archive updates and frontend restarts. Pane widths continue to use localStorage with the existing viewport clamp. They do not follow the user after browser storage is cleared.

## Risks / Trade-offs

- [Existing browser choices differ from database defaults] -> Apply the database response or documented defaults before rendering signed-in content; never import the old browser values.
- [Preference API is unavailable] -> Use defaults for this load, keep controls usable, and retry on the next load.
- [Browser storage is cleared] -> Resizable pane widths return to their defaults by explicit product choice; they never generate preference API writes.
- [Concurrent updates] -> PATCH only the field changed; the same field uses last-write-wins semantics.

## Migration Plan

Apply the additive `users_preferences` table migration before deploying the new Control Plane and frontend. Existing users have no row and receive defaults; they choose their durable settings again. Rollback to older application images leaves the table unused. Dropping it would discard choices saved after rollout. The operator note specifies the sequence, validation, rollback and browser-local width behavior.
