## Context

The approved first journey ends at provisioning and organization membership display. Keeping the rest of the Python UI operational was explicitly withdrawn. No cross-store role projection or Python admission callback is allowed. Root already has a durable, exclusive SQL claimant reservation and guarded OpenFGA writes.

## Goals / Non-Goals

**Goals:** one real first-login journey, including explicit versioned consent, durable platform-only root, actual ZIP import, logout and another person's organization memberships. Record the complete Fred journey inventory without claiming its later stages are implemented in Rust.

**Non-Goals:** compatibility adapters, old admin screens, organization auto-enrollment, default teams, personal-space creation on login, account suspension administration, platform allowlists/invitations/delegation, content workflows. These remain separately scoped business stages, not implicit behavior in this slice.

## Decisions

- Add a new SQL migration for per-subject accepted terms version and timestamp. No user-directory copy. An identical repeat preserves the timestamp; a changed configured version requires a fresh explicit acceptance. POST submits the version actually displayed and rejects a stale version with 409.
- Keep `app.gcu_version` and the existing localized frontend legal documents. Null disables terms, as in Fred; the shipped manager configuration and browser fixture enable v1. Refuse malformed configured versions. Consent creates no spaces or roles and import never writes consent.
- Manager owns public startup authentication/configuration, authenticated onboarding state and acceptance. Apply a shared server-side terms gate to business handlers, including bootstrap and ZIP import; identity/consent reads stay reachable before acceptance. Bootstrap and consent require the person's own credential, rejecting service principals and delegated assertions.
- Preserve the existing stronger Rust bootstrap reservation, completed marker and error semantics. Its claimant is not automatically enrolled anywhere. Public status is derived from durable completion, never a role count.
- Use a manager frontend entry with existing presentation primitives, terms content, bootstrap form and provisioning page. Extract reusable presentation where needed; do not mount the legacy product shell, add a backend-selection toggle or pretend manager DTOs are Python DTOs. The home view lists only spaces returned for the caller, including their organization. Root may have no spaces.
- No OpenFGA operations are added by public configuration or terms reads/writes. Business checks retain existing cost plus one indexed SQL consent lookup per admitted request. Bootstrap's existing guard/read/write budget is unchanged. Organization display reuses `/me/spaces` and its existing enumeration cost.

## Risks / Trade-offs

- A stale browser can hold an old version: the server rejects its acceptance, the UI requests reload rather than recording unseen terms.
- Identity and application membership are distinct: a Keycloak identity and acceptance row do not imply an organization or personal space.
- The experimental entry intentionally exposes only the implemented journey. Tests must reject any control-plane/knowledge-flow network request rather than mocking them.
- Legal text and version are deployment assets: changing text requires a version bump. This slice supplies mechanics and the existing sample text, not organization-specific legal terms.

## Migration Plan

Run the additive SQL migration at manager startup, regenerate the client, rebuild manager and frontend together. Set `app.gcu_version` in the normal manager configuration (including k3d). Existing manager roles/spaces stay unchanged; existing identities accept the configured version at next access. No applied migration is edited and no Python data is copied. Older manager binaries reject unknown applied migrations: use a forward fix, or restore a coordinated pre-upgrade SQL/OpenFGA backup with the prior application pair. Do not remove applied migration records to force a rollback.
