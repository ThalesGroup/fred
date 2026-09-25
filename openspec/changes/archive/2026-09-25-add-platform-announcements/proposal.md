## Why

Platform operators have no way to tell users anything at runtime. The only
announcement surface today is `InfoBanner` — a single, non-dismissible banner
whose content lives in Helm values (`platform.frontend.info_banner`), so
changing a word means editing YAML and redeploying the control-plane. That
makes it unusable for the thing operators actually need: announcing a
maintenance window, a new feature, or an incident, now, without a release.

This change turns that one deploy-time banner into a platform-admin-managed
collection of announcements, editable from the admin console and dismissible
by each user.

## What Changes

- **New admin page** at `/admin/annonces`, gated by `requires="admin"`, listing
  every announcement with create / edit / delete and an enable-disable toggle.
- **New announcement model** in the control-plane, persisted in Postgres:
  - `severity`: `info | warning | error | success` — the same `Literal` the
    neighbouring `UploadWarning` already uses. Each severity carries a fixed
    icon (`info`, `warning`, `error`, `check_circle`), not an authored one.
  - `title`, `description_short`, `description_long`: locale → text maps
    (`fr`, `en`) resolved with an `en` fallback, matching how `info_banner` and
    `upload_warning` already store their text.
  - `enabled` and `dismissible` flags.
  - `content_version`, bumped on every content edit — the key that makes an
    edited announcement reappear for users who had dismissed it.
- **Markdown descriptions.** Both descriptions are markdown, authored in the
  admin page with the existing `ProseMdxEditor` (full prose toolbar for
  `description_long`, a reduced bold/italic/link toolbar for
  `description_short`) and rendered with the existing `MarkdownRenderer`.
- **Banner stack.** Every enabled announcement renders as a banner at the top
  of the app, stacked, sorted by severity then creation date. Each banner shows
  its icon, title, `description_short`, and an actions toolbar:
  - a "Plus d'info" button, present only when `description_long` is non-empty,
    opening the central `Dialog` molecule with the full markdown and a
    "Fermer" button that closes the dialog (backdrop click closes it too);
  - a close icon button, present only when `dismissible`, playing the existing
    300 ms collapse before unmount.
- **Delivery.** The frontend polls active announcements every ~60 s and
  refetches on window focus. No new SSE channel.
- **Dismissal** is persisted in `localStorage`, keyed by announcement id +
  `content_version`. Per-browser by design; no server-side per-user state.
- **BREAKING — `platform.frontend.info_banner` is removed.** Its Pydantic model,
  its field on the public `/control-plane/v1/frontend/config` response, its
  Helm values block and its configuration samples all go. The `InfoBanner`
  component is rewritten as the renderer for one announcement. Deployments
  currently setting `info_banner` lose their banner on upgrade and must
  recreate it from the admin page.
- **BREAKING — announcements are post-authentication only.** Today's
  `InfoBanner` renders above the guards, so it also shows on the GCU-acceptance
  and root-bootstrap screens. Announcements are admin-authored content served
  from an authenticated endpoint, so the stack moves inside the guards. The
  ability to address a user who cannot log in is deliberately given up.

Out of scope for this slice, deliberately: scheduling (start/end dates) — the
planned next change. The model must not preclude it, so nothing here assumes
`enabled` is the only thing that decides visibility.

## Capabilities

### New Capabilities

- `platform-announcements`: platform-admin-authored announcements and how they
  are delivered to, rendered for, and dismissed by authenticated users.

### Modified Capabilities

None. `platform.frontend.info_banner` is documented in the configuration
samples and the control-plane product contract, not in an OpenSpec capability
spec, so its removal changes no existing spec.

## Impact

**Control-plane backend** (`apps/control-plane-backend/`)

- New `control_plane_backend/announcements/` module (`api.py`, `schemas.py`,
  `service.py`, `store.py`), modelled on `platform_prompt/`.
- New `control_plane_backend/models/announcement_models.py` + one Alembic
  revision on the control-plane tree, re-parented onto the current `swift` head
  so the tree keeps exactly one head.
- Authorization through `OrganizationPermission.CAN_MANAGE_PLATFORM` for the
  admin routes; the read route is available to any authenticated user.
- Audit lines via `emit_audit_log` on create / update / delete / toggle.
- Removal: `InfoBanner` / `InfoBannerLink` from `config/models.py`, the
  `info_banner` field from `product/schemas.py` and `product/service.py`, and
  the related assertions in `tests/test_main.py`.

**Frontend** (`apps/frontend/`)

- New `AnnouncementsPage` under `rework/components/pages/admin/`, a route in
  `common/router.tsx` and an entry in `AdminNavbar.tsx`.
- `InfoBanner` reworked into the announcement renderer plus a new stack
  container, moved from above the guards to inside them in `app/App.tsx`.
- Dismissal helper over `localStorage`; polling hook over the generated RTK
  query.
- `info_banner` removed from `common/config.tsx` (`AppConfig`, `getInfoBanner`).
- Regenerated `controlPlaneOpenApi.ts` (`make update-control-plane-api`) and
  friendly aliases in `controlPlaneApiEnhancements.ts`.
- New `fr` / `en` keys in `locales/*/translation.json`.

**Deployment & docs**

- `deploy/charts/fred/values.yaml`: `info_banner` block removed.
- `apps/control-plane-backend/config/configuration.yaml` and
  `configuration_prod.yaml`: `info_banner` samples removed.
- `docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md`: dated entry for the
  new routes and the removed `/frontend/config` field.
- `docs/swift/ux/COMPONENT-UX.md`: the banner stack and its dialog.
