## 1. Control-plane data layer

- [x] 1.1 Add `control_plane_backend/models/announcement_models.py` with the `announcement` table (id, severity, localized title/description_short/description_long JSON maps, enabled, dismissible, content_version, created_at, updated_at, updated_by) and register it in `models/table_ownership.py`; verify `python -c "import control_plane_backend.models.announcement_models"` succeeds and the table appears in the metadata.
- [x] 1.2 Generate the Alembic revision creating the table, parented on the current control-plane head; verify `alembic heads` reports exactly one head and `alembic upgrade head` then `alembic downgrade -1` both run clean against local Postgres.
- [x] 1.3 Add `announcements/store.py` with pure CRUD (list, get, create, update, delete, set_enabled) and no authorization checks, following `platform_prompt/store.py`; verify with store unit tests covering create → list → update → delete round-trips.

## 2. Control-plane service and API

- [x] 2.1 Add `announcements/schemas.py`: the `Announcement` response model, create/update request models, the `info | warning | error | success` severity `Literal` reusing the same values as `config.models.UploadWarning`, and validation rejecting an empty `title`/`description_short` for every locale; verify schema unit tests cover the rejection cases in the delta spec.
- [x] 2.2 Add `announcements/service.py` gating every mutation on `OrganizationPermission.CAN_MANAGE_PLATFORM` via `rebac.check_user_permission_or_raise`, emitting `emit_audit_log` on create/update/delete/toggle, and bumping `content_version` only when a content-bearing field actually changed; verify tests assert a text edit bumps the version and an `enabled` toggle does not.
- [x] 2.3 Add `announcements/api.py` with the admin routes under `/admin/platform/announcements` and the authenticated read route returning enabled announcements only; register the router in `main.py`; verify route tests cover the administrator, non-administrator and unauthenticated cases from the delta spec.
- [x] 2.4 Run `make code-quality` and `make test` in `apps/control-plane-backend`; verify both are green.

## 3. Generated client

- [ ] 3.1 Run `cd apps/frontend && make update-control-plane-api` and commit the regenerated `controlPlaneOpenApi.ts`; verify the announcement types and hooks are present in the diff and that no hand-written type duplicates them.
- [ ] 3.2 Add friendly aliases for the announcement hooks in `controlPlaneApiEnhancements.ts`, with the read query configured for a 60 s `pollingInterval` and `refetchOnFocus`; verify `make type-check` passes.

## 4. Banner rendering

- [ ] 4.1 Rework `InfoBanner` into an announcement renderer taking an announcement as a prop — severity-driven colour and icon (`info`, `warning`, `error`, `check_circle`), localized title, `description_short` through `MarkdownRenderer`, actions toolbar — keeping the existing 300 ms collapse and its `prefers-reduced-motion` handling; verify the existing and extended component tests pass.
- [ ] 4.2 Add the dismissal helper over `localStorage`, keyed by announcement id + `content_version`, with every read and write wrapped so unavailable storage degrades to "never dismissed"; verify unit tests cover persistence, the version bump making a banner reappear, and the throwing-storage path.
- [ ] 4.3 Add the stack container that queries active announcements, filters out dismissed ones, and orders by severity then creation date; verify tests cover the ordering and the empty-set case rendering nothing.
- [ ] 4.4 Add the more-info dialog on the central `Dialog` molecule — title plus `description_long` through `MarkdownRenderer`, a "Fermer" button, backdrop dismissal — shown only when `description_long` is non-empty; verify tests cover its presence, its absence, and that closing it leaves the banner up.
- [ ] 4.5 Mount the stack inside the guards in `app/App.tsx`, replacing the pre-auth `<InfoBanner />`, and confirm `.appShell`/`.appContent` still push content down rather than overlay it; verify no banner renders on the GCU and bootstrap screens.

## 5. Admin page

- [ ] 5.1 Add `AnnouncementsPage` under `rework/components/pages/admin/` listing announcements with their severity, enabled state and enabled count, plus create/edit/delete and the enable toggle; verify page tests cover the list, the toggle and the delete confirmation.
- [ ] 5.2 Add the announcement editor form with FR/EN tabs for the three text fields, `ProseMdxEditor`'s shared `proseMdxPlugins()` for both descriptions, `ProseToolbarButtons()` for `description_long` and a reduced undo/bold/italic/link toolbar for `description_short`; verify tests cover locale switching and that submitting with an empty short description is refused.
- [ ] 5.3 Register the `/admin/annonces` route in `common/router.tsx` behind `Protected requires="admin"` and add the `AdminNavbar.tsx` entry with the same `requires`; verify the entry is hidden for a non-admin.
- [ ] 5.4 Add the `fr` and `en` keys to `locales/*/translation.json`; verify no hardcoded user-facing string remains in the new components.

## 6. Remove the deploy-time info banner

- [ ] 6.1 Remove `InfoBanner`/`InfoBannerLink` from `control_plane_backend/config/models.py`, the `info_banner` field from `product/schemas.py` and `product/service.py`, and the related assertions in `tests/test_main.py`; verify `make test` is green in `apps/control-plane-backend`.
- [ ] 6.2 Remove `info_banner` from `common/config.tsx` (`AppConfig`, `getInfoBanner`) and every remaining reference; verify `grep -rn info_banner apps/frontend/src` returns only the regenerated client's removal in the diff, and `make type-check` passes.
- [ ] 6.3 Remove the `info_banner` block from `deploy/charts/fred/values.yaml`, `config/configuration.yaml` and `config/configuration_prod.yaml`; verify `grep -rn info_banner deploy apps/control-plane-backend/config` returns nothing.

## 7. Verification and close-out

- [ ] 7.1 Run `make code-quality` from the monorepo root and `make test` in both touched projects; verify all green.
- [ ] 7.2 Run the `fred-performance-reviewer` skill over the read route and the polling hook — a per-tab request every 60 s under concurrent load — and address anything it raises.
- [ ] 7.3 Run `/code-review` on the full branch diff at default effort or higher and address the findings.
- [ ] 7.4 Add the dated entry to `docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md` for the new routes and the removed `/frontend/config` field, and document the banner stack and its dialog in `docs/swift/ux/COMPONENT-UX.md`.
- [ ] 7.5 Record verification evidence in the change, then `openspec archive add-platform-announcements`; close the GitHub issue.
