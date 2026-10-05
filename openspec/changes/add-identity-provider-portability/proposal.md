## Why

Fred only works with Keycloak today. Token validation is standard (PyJWT + JWKS), but everything around it assumes Keycloak:

- endpoints are built as `{realm_url}/protocol/openid-connect/{certs,token,auth}` in eight places;
- identity and roles are read from Keycloak-specific claims (`resource_access.<client>.roles`, `preferred_username`) and the strict audience is assumed to equal the login `client_id`;
- the user directory (list, search, display names, counts, username resolution, existence checks) is the Keycloak Admin API;
- the frontend uses `keycloak-js` in realm mode.

Some customers refuse to run Keycloak in their stack and require Fred to use their own identity provider directly (first target: Microsoft Entra ID; later: Okta and other OIDC providers). We want **one codebase, one image, and a per-deployment configuration file**, without a fork.

The delegation work on `test-23-09` (`add-delegated-agent-execution`) already removes the only architectural blocker: agents no longer hold or refresh the person's token and call other services with a workload token plus a `person`, `run`, `agent` grant. The remaining work is configuration-level portability plus a Postgres-backed user directory.

**Guiding constraint: minimal change.** Every new setting is optional and its default reproduces today's Keycloak behavior exactly. Existing deployments need no configuration change, no data migration and see no behavior change. The browser adapter changes for Keycloak, while configured identity and directory defaults are preserved. No renames (`KeycloakUser`, `realm_url`, `KeyCloakService` stay), no broad refactor, no new abstraction layer beyond what is required.

## What Changes

- Add `provider: keycloak | oidc` (default `keycloak`) to `security.user` and `security.m2m`. With `oidc`, `realm_url` is treated as the OIDC issuer and endpoints are resolved once at startup from `/.well-known/openid-configuration`, with optional explicit `jwks_url` / `token_url` overrides.
- Make token interpretation configurable with Keycloak defaults: identity claim (`sub`), username claim (`preferred_username`), name/email claims, roles claim path (`resource_access.<client_id>.roles`), and an optional `audience` distinct from `client_id`. Non-UUID identity values from an `oidc` provider are mapped deterministically to a UUID (`uuid5`), statelessly, so agent pods need no database.
- Add `scope` to `security.m2m` (required by Entra client credentials) and route every token-endpoint consumer (workload tokens, `user_token_refresher.py`, `outbound.py`) through the resolved token endpoint.
- Refuse unsafe or silently broken combinations at startup: `oidc` + `delegation.service_accounts_only`, `oidc` + delegation without `caller_roles_claim`, `oidc` + `user_directory: keycloak`.
- Add `security.user_directory: keycloak | local` (default `keycloak`). With `local`, the Keycloak Admin API is never called: Fred records a minimal identity snapshot (username, email, first/last name) in the existing Postgres `users` table on authenticated requests, and serves list, search, display names, counts, `users.json` username resolution and existence checks from it. User creation is refused with an explicit reason; user deletion suspends the person in Fred and leaves the identity-provider account untouched. Local suspension is enforced independently of delegation; deletion is refused when no engine can enforce it.
- The declarative `users.json` import never creates identities in `local` mode: an entry that cannot be resolved and would have been created is refused with the same `managed_by_identity_provider` reason, and the import fails closed as it does today.
- First-party applications configured from the environment (`security/env_config.py`) accept the same provider settings as YAML-configured services.
- Frontend: expose `provider`, `scope`, `user_directory` and the identity and roles claims through `/frontend/config`. With `oidc`, `oidc-client-ts` handles Authorization Code with PKCE, refresh and provider logout behind the existing `KeyCloakService` facade; Keycloak SHALL use the same `oidc-client-ts` browser lifecycle; `provider: keycloak` remains a compatibility setting for endpoint and claim defaults. The browser derives the **same user id as the backends** (configured claim, `uuid5` fallback), so personal-space ids stay consistent, and reads roles from the configured claim. Keycloak-only features (password-grant self-test probe, user creation button) are hidden.
- Knowledge Flow no longer refuses to start when the issuer is not a `…/realms/<realm>` URL in `oidc` mode.
- Add local test tooling in the sibling `fred-deployment-factory` repository: a Keycloak "generic OIDC shape" profile, an optional non-Keycloak mock OIDC provider, and a script that records the demo users in the local directory before import.
- Document provider setup, with a complete Microsoft Entra ID recipe (app registrations, v2 tokens, scope, audience, app roles, token lifetime).

## Capabilities

### New Capabilities

- `identity-provider-configuration`: provider switch, endpoint resolution, claim mapping, audience, workload token scope, stateless identity normalization and startup refusal of inconsistent configurations.
- `local-user-directory`: Postgres-backed identity snapshot and directory operations when the Keycloak Admin API is not available.
- `frontend-oidc-login`: generic OIDC login, logout and refresh in the browser, identity and roles consistent with the backends, and hiding of Keycloak-only features.
- `local-idp-test-bench`: reproducible local environments that exercise the generic provider paths without a cloud tenant.

### Modified Capabilities

The browser lifecycle is unified, including Keycloak; existing configuration and identity defaults remain supported.

## Non-Goals

- No Keycloak-specific CLI rework (`fred_core/cli/auth.py`, `control_plane_backend/cli`): these stay Keycloak-only developer tools.
- No SCIM endpoint, no Microsoft Graph directory lookup, no invitation workflow (people who never signed in are not searchable in `local` mode).
- No renaming of Keycloak-named symbols, settings or files.
- No change to OpenFGA models, existing tuples or the delegation protocol.
- Keycloak-specific administration and directory integrations remain available when explicitly configured; unifying browser OIDC does not remove them.

## Impact

- `libs/fred-pod`: security configuration models, workload token endpoint.
- `libs/fred-core`: `security/oidc.py`, `security/delegation.py` startup checks, `security/outbound.py`, Keycloak admin client guard, `users` model and store.
- `libs/fred-runtime`: token endpoint used by `user_token_refresher.py`; workload token builder.
- `libs/fred-sdk`: workload token builder for knowledge-base pods.
- `apps/control-plane-backend`: users and teams services, `/frontend/config`, Alembic migration, workload token builder.
- `apps/knowledge-flow-backend`: users service, startup realm check.
- `apps/control-plane-backend` import: identity provisioning phase of `import_export/importer.py`.
- `libs/fred-core/fred_core/security/env_config.py`: environment-based first-party configuration.
- `apps/frontend`: `KeycloakService.ts` (construction, user id, roles), `common/config.tsx`, user administration and self-test pages.
- Deployment and docs: Helm values and schemas (regenerated), `docs/swift/platform/KEYCLOAK.md`, new `docs/swift/platform/IDENTITY-PROVIDERS.md`.
- `fred-deployment-factory` (sibling repository, branch matching `test-23-09`): new optional Make targets and scripts for local testing; no change to the default stack.
- Estimated size: ~370 lines of production code and ~420 lines of tests in `fred`, plus ~200 lines of scripts in `fred-deployment-factory`, excluding generated schemas and clients.

## Agreed follow-up (2026-09-29)

Use one OIDC browser implementation for all providers, including Keycloak.
Record authenticated human profiles in the local directory on the first
control-plane request, including `/user` before CGU acceptance. Recording a
profile does not accept CGU, grant a role or reopen platform-admin bootstrap.
The common browser lifecycle and pre-CGU snapshot are implemented; automated persistence/delegation checks pass and real browser verification remains pending.
