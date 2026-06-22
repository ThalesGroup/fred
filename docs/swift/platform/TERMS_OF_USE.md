# Terms Of Use / CGU Gating

This page documents the current Fred behavior for Terms of Use acceptance
gating, including what is configurable today and what is still missing.

## Purpose

Fred can require an authenticated user to accept the currently active Terms of
Use before accessing the product.

In the codebase, this currently appears under mixed naming:

- `gcu_version` in backend/runtime configuration and bootstrap payloads
- `cguValidated` in some frontend/control-plane DTOs

Those names all refer to the same feature: Terms of Use / CGU acceptance
versioning.

## Is It Optional?

Yes. The feature is optional.

Terms gating is disabled when either of these is true:

- `app.gcu_version` is unset / `null`
- user security is disabled (`security.user.enabled: false`)

This means:

- local developer deployments do not need it
- technical integration environments do not need it unless product owners want
  explicit acceptance testing there
- production deployments can enable it when explicit acceptance is required

## How To Enable It

Enable the feature in `control-plane-backend` by setting a non-empty
`app.gcu_version`.

Example:

```yaml
app:
  name: Control Plane Backend
  base_url: /control-plane/v1
  address: 0.0.0.0
  port: 8222
  log_level: info
  gcu_version: V1
```

Disable it by leaving the field unset or explicitly setting it to `null`.

Example:

```yaml
app:
  gcu_version: null
```

## What Happens When Enabled

The current behavior is:

1. `control-plane` exposes the active `gcu_version` on the **public pre-auth**
   surface `GET /control-plane/v1/frontend/config` (see FRONT-10). The value is
   the *effective* one: `null` whenever gating is off (`security.user.enabled`
   false or `app.gcu_version` unset).
2. the frontend reads it at startup (Stage 0, before authentication) via
   `getGcuVersion()`. It is **not** read from `/frontend/bootstrap`: that
   endpoint is authenticated and itself CGU-gated (it returns `403
   user_not_accept_gcu` until acceptance), so it cannot deliver the version
   needed to render the acceptance page — a chicken-and-egg the public surface
   resolves.
3. if the current user has not accepted the same version yet, the frontend
   routes the user to the dedicated GCU page instead of the normal app shell.
   The user's accepted version is read from `GET /control-plane/v1/user`
   (`cguValidated`), which uses `get_current_user_without_gcu` so it stays
   reachable before acceptance.
4. `POST /control-plane/v1/gcu` stores acceptance of the active version for the
   authenticated user (also `get_current_user_without_gcu`, so it is writable
   before the stricter gate passes).
5. secured backend/runtime request paths (`get_current_user`) then check that
   the persisted accepted version matches the configured active version.

> Note: `FrontendBootstrap` still carries a `gcu_version` field, but it is a
> post-auth informational mirror (used by the control-plane CLI) and must not be
> used to gate the UI. The authoritative pre-auth source is
> `FrontendConfig.gcu_version`.

Operational consequence:

- changing `gcu_version` from `V1` to `V2` forces users to accept the updated
  Terms of Use again

## Which Deployments Need It?

Not all deployments need it.

Recommended rule of thumb:

- `dev/local`: disabled
- `internal beta`: optional, depending on whether you want product-level
  validation of the acceptance flow
- `production/internal`: enable when the deployment must present and record a
  controlled Terms of Use version
- `production/external`: usually enable, subject to the product/legal owner

The feature is therefore deployment-driven, not hard-mandatory for every Fred
installation.

## What A Deployment Owner Can Customize Today

Today, a deployment owner can:

- decide whether the feature is enabled
- choose the active version string (`V1`, `2026-04`, etc.)
- force re-acceptance by changing that version

## Current Limitation: Terms Text Is Not Yet Configurable

Today there is no documented, first-class deployment configuration that lets a
project owner provide their own Terms of Use text to the frontend.

Current state:

- the frontend has a dedicated GCU page and acceptance button flow
- the page title/button labels are translated
- but the actual Terms content is not sourced from deployment configuration
- there is no documented field such as:
  - inline markdown text
  - file path to a Terms document
  - URL to a deployment-owned Terms page

In other words:

- the **acceptance mechanism exists**
- the **deployment-owned Terms content contract does not yet exist**

## What Is Missing For A Complete Production Contract

For production-grade deployments, Fred should ideally support one explicit
Terms content source owned by the deployment, for example:

- a markdown file path in configuration
- a plain text / markdown field in control-plane config
- a deployment-owned URL exposed in frontend bootstrap

Until that is implemented, enabling `gcu_version` gives you versioned
acceptance gating, but not yet a documented way to inject your own Terms text
without changing frontend code.

## Related Components

- control-plane publishes the active version on the public pre-auth
  `/frontend/config` surface (authoritative for the guard); the authenticated
  `/frontend/bootstrap` mirrors it for post-auth/CLI display only
- control-plane persists acceptance in the shared user store
- frontend guard (`GcuGuard`) redirects non-accepted users to the GCU page
- secured request paths enforce the persisted accepted version when configured

## Recommended Next Step

If your deployment needs project-owner-authored Terms text, implement and
document one explicit content source before relying on this feature as a full
production legal/operational contract.
