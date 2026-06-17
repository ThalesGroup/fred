# RFC: Backend-driven frontend auth config (FRONT-08)

**Status:** Implemented (2026-06-16) on branch `1748-front-08-frontend-auth-config` — pending review
**Author:** Simon Cariou
**Date:** 2026-06-16
**ID:** FRONT-08
**Backlog:** `docs/swift/backlog/FRONTEND-BACKLOG.md §14`
**Contract impact:** `docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md §3.1` — adds a new
public pre-auth surface alongside the existing authenticated `FrontendBootstrap`.

---

## 1. Problem

Today the frontend's "is user security enabled?" decision is hand-edited in a static
asset, `apps/frontend/public/config.json`:

```json
{
  "frontend_basename": "/",
  "user_auth": {
    "enabled": true,
    "realm_url": "http://app-keycloak:8080/realms/app",
    "client_id": "app"
  }
}
```

`loadConfig()` in `apps/frontend/src/common/config.tsx` reads `user_auth.enabled` and, when
true, calls `createKeycloakInstance(realm_url, client_id)` which sets the module-level
`isSecurityEnabled` flag in `apps/frontend/src/security/KeycloakService.ts`. When false, the
app boots in dev mode with a synthetic local token.

The backend **already** owns this exact information. `fred_core.security.SecurityConfiguration`
(`libs/fred-core/fred_core/security/structure.py:95`) carries:

```python
class UserSecurity(BaseModel):
    enabled: bool = True
    realm_url: AnyUrl
    client_id: str
```

So `config.json.user_auth` is a hand-maintained duplicate of `security.user` on the
control-plane backend. Switching a deployment (or a dev) between secure and dev mode means
editing the static frontend file by hand and keeping it in sync with the backend YAML — the
two can drift, and "dev mode" requires touching a checked-in asset.

The goal: make the backend the single source of truth for whether the frontend enables
Keycloak, removing the manual `config.json` edit.

### 1.1 This is a parity regression, not a new feature

The production branch (`main`) already does exactly this. There, `frontend/public/config.json`
contains **only** `frontend_basename`, and `loadConfig()` fetches an **unauthenticated** backend
route for everything else, including `user_auth`:

```python
# agentic-backend/agentic_backend/core/chatbot/chatbot_controller.py (origin/main)
@router.get("/config/frontend_settings", summary="Get the frontend dynamic configuration")
def get_frontend_config() -> FrontendConfigDTO:          # no Depends(get_current_user)
    cfg = get_configuration()
    return FrontendConfigDTO(
        frontend_settings=cfg.frontend_settings,
        user_auth=UserSecurity(
            enabled=cfg.security.user.enabled,
            realm_url=cfg.security.user.realm_url,
            client_id=cfg.security.user.client_id,
        ),
        is_rebac_enabled=get_rebac_engine().enabled,
    )
```

The swift migration moved frontend bootstrap/configuration ownership to `control-plane-backend`
(per `CONTROL-PLANE-PRODUCT-CONTRACT.md §2.1`) but, in doing so, regressed `user_auth` from a
backend-served value into a hand-edited static asset. This RFC restores the existing pattern on
the swift owner — it does not introduce a new architecture.

**Is an unauthenticated config route a problem?** No. It is the shipped production pattern, and
everything it exposes is public bootstrap data the browser needs *before* login: the Keycloak
`realm_url`/`client_id` belong to a **public PKCE client** (not secret by design), and
feature/display values are non-sensitive. No secret (client secret, M2M credentials, ReBAC
internals) is exposed.

## 2. Constraint that rules out the existing bootstrap route

The natural instinct is to put the flag in `GET /control-plane/v1/frontend/bootstrap`. It
cannot go there: that endpoint is authenticated
(`Depends(get_current_user)`, `apps/control-plane-backend/control_plane_backend/product/api.py`).
To know whether to authenticate, the frontend would have to call it *before* authenticating —
a chicken-and-egg. The auth decision must come from an **unauthenticated** surface, consumed at
Stage 0 (before Keycloak init), per `FRONTEND-BACKLOG.md §1.2–1.3`.

## 3. Proposed solution

Add a dedicated **public (unauthenticated)** pre-auth endpoint on the control-plane backend:

```
GET /control-plane/v1/frontend/config        (no auth)
```

Response model `FrontendConfig`:

```python
class FrontendUserAuthConfig(BaseModel):
    enabled: bool
    realm_url: str | None = None   # present only when enabled
    client_id: str | None = None   # present only when enabled

class FrontendConfig(BaseModel):
    user_auth: FrontendUserAuthConfig
```

The handler derives `user_auth` directly from `deps.configuration` `security.user`
(`UserSecurity`). `realm_url`/`client_id` are emitted only when `enabled` is true, so a dev
deployment leaks no realm details.

The frontend's Stage 0 changes (`config.tsx`, `index.tsx`):

1. `frontend_basename` stays in `/config.json` — it is a pre-network static value needed for
   router setup, so the static asset is not removed.
2. `loadConfig()` fetches `GET /control-plane/v1/frontend/config` for `user_auth` instead of
   reading it from `/config.json`.
3. The rest of the flow is unchanged: `user_auth.enabled` → `createKeycloakInstance(...)`;
   otherwise dev-token mode. `KeycloakService` is untouched.

Net effect: the auth decision is owned by the backend YAML (`security.user`), already the
source of truth for the backend's own JWT validation. No more hand-edited `config.json` to
toggle dev mode.

### 3.1 Failure behavior

If the `/frontend/config` fetch fails, startup aborts with an error — identical to today's
behavior when `/config.json` is missing or malformed (`loadConfig()` throws, caught in
`index.tsx`, app does not render). The endpoint is public and served by the same control-plane
the app cannot function without, so a hard failure is correct and consistent.

### 3.2 `user_auth` removed from `config.json`

After this change, `config.json` carries only `frontend_basename` (plus any existing
`feature_flags`/`properties`). The `user_auth` block is removed from the committed
`public/config.json`. `loadConfig()` keeps tolerating an absent `user_auth` in the raw config
(it already defaults to `{ enabled: false }`), but the live value comes from the endpoint.

## 4. Alternatives considered

### 4.1 Make `/frontend/bootstrap` conditionally public

Return `user_auth` when unauthenticated and the full payload when authenticated.
**Rejected:** mixes a pre-auth concern into a frozen, authenticated, product-shaped payload;
complicates the dependency (`get_current_user` would have to become optional); and the contract
explicitly scopes `FrontendBootstrap` to post-auth product state. A separate public surface
keeps the boundary clean.

### 4.2 Keep `config.json` but generate it from backend config at deploy time

A build/deploy step renders `config.json` from the backend YAML. **Rejected:** still a static
artifact that can drift, adds deploy-time tooling, and does not give a dev a runtime toggle —
it just moves the duplication into the pipeline.

### 4.3 Status quo (manual edit)

**Rejected** — this is the pain the request targets.

## 5. Files touched (planned)

| File | Change |
|---|---|
| `apps/control-plane-backend/control_plane_backend/product/schemas.py` | Add `FrontendUserAuthConfig` + `FrontendConfig` models |
| `apps/control-plane-backend/control_plane_backend/product/api.py` | Add public `GET /frontend/config` (no `get_current_user`) |
| `apps/control-plane-backend/control_plane_backend/product/service.py` | `build_frontend_config(configuration)` deriving `user_auth` from `security.user` |
| `apps/frontend/src/common/config.tsx` | `loadConfig()` fetches `/control-plane/v1/frontend/config` for `user_auth` |
| `apps/frontend/public/config.json` | Remove `user_auth` block (keep `frontend_basename`) |
| `apps/frontend/src/<generated controlPlaneOpenApi>` | Regenerate from OpenAPI (do not hand-edit) |
| `deploy/charts/fred/values.yaml` | Remove `user_auth` from `applications.frontend.configuration.config_json` (keep `frontend_basename`); control-plane `security.user` is already the source |
| `deploy/local/k3d/values-local.yaml` | Same removal of frontend `config_json.user_auth` |
| `deploy/charts/fred/values.schema.json` | Drop the frontend `config_json.user_auth` schema block (regenerate, do not hand-edit if generated) |
| `docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md §3.1` | Document the public `FrontendConfig` pre-auth surface |
| `docs/swift/backlog/FRONTEND-BACKLOG.md §1.2/§1.3/§14` | Amend Stage 0/Stage 1 wording + new phase entry |

> **Helm note:** the frontend `config.json` is rendered from
> `applications.frontend.configuration.config_json` via
> `deploy/charts/fred/templates/configmap-frontend.yaml`. Removing `user_auth`
> there is required so the chart does not re-pin the static value; the
> control-plane deployment's `security.user` (already configured for backend JWT
> validation) becomes the sole source. No new Helm value is introduced.

Open question for confirmation: must the endpoint be reachable without CORS/auth from the
dev Vite origin (it should — it's already a same-origin proxied path), and do we want
`m2m`/`rebac` exposure too (proposal: **no**, user auth only — keep the surface minimal).

## 6. Acceptance criteria

- [ ] `GET /control-plane/v1/frontend/config` returns `{ user_auth: { enabled, realm_url?, client_id? } }` with no auth header.
- [ ] When `security.user.enabled = false`, response omits `realm_url`/`client_id` and the frontend boots in dev mode without a Keycloak redirect.
- [ ] When `security.user.enabled = true`, the frontend initializes Keycloak from the endpoint values — no `user_auth` needed in `config.json`.
- [ ] `config.json` no longer contains a `user_auth` block; toggling dev/secure mode requires only the backend `security.user.enabled` flag.
- [ ] Startup fails cleanly (same as a missing `config.json`) if the endpoint is unreachable.
- [ ] `make code-quality` + `make test` green in `apps/control-plane-backend` and `apps/frontend`; OpenAPI regenerated via the documented command.
