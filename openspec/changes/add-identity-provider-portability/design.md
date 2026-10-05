## Context

See [proposal.md](proposal.md) for the objective. This change is based on the `test-23-09` branch, which contains `add-delegated-agent-execution`. It assumes that delegation is enabled (`act_for_people` / `accept_delegated_calls`) on deployments that do not use Keycloak, because that is what removes server-side refresh of a person's token.

Current Keycloak coupling (verified on `test-23-09`, commit `6e8858f0`):

| Area | Location | Coupling |
|---|---|---|
| JWKS URL | `libs/fred-core/fred_core/security/oidc.py` `initialize_user_security` | `f"{realm_url}/protocol/openid-connect/certs"` |
| Startup log | same function | `split_realm_url()` raises `ValueError` on a non-realm URL |
| Audience | `oidc.py` `decode_jwt` | expected audience = `client_id` (+ delegation audience) |
| Roles | `oidc.py` `decode_jwt` | `payload["resource_access"][client_id]["roles"]` |
| Username | `oidc.py` `decode_jwt` | `preferred_username` |
| Identity | `oidc.py` `_parse_user_uuid`, `users` table | `sub` must be a UUID for the user store |
| Workload token | `libs/fred-pod/fred_pod/security/backend_to_backend_auth.py` `M2MAuthConfig.token_url` | `f"{realm_url}/protocol/openid-connect/token"`; built in `control_plane_backend/app/context.py`, `fred_runtime/common/outbound_credentials.py`, `fred_sdk/knowledge_base/configuration.py` |
| Person token refresh | `libs/fred-runtime/fred_runtime/runtime_support/user_token_refresher.py`, called from `integrations/v2_runtime/adapters.py` via `get_keycloak_url()` | hard-coded token path |
| Client credentials helper | `libs/fred-core/fred_core/security/outbound.py` `ClientCredentialsProvider` | `keycloak_base` + `realm` |
| Delegation | `libs/fred-pod/fred_pod/security/delegation.py`, `libs/fred-core/fred_core/security/delegation.py` | default roles path `resource_access.<audience>.roles`; `service_accounts_only` uses Keycloak markers |
| Directory | `control_plane_backend/users/service.py`, `teams/service.py`, `knowledge_flow_backend/features/users/users_service.py` | Keycloak Admin API (12 call sites) |
| User deletion | `control_plane_backend/users/api.py` delete route | obtains the write admin client **before** the standing ban; raises when the Admin API is disabled |
| Import identities | `control_plane_backend/import_export/importer.py` `_provision_bundle_identities` | creates missing Keycloak users through `create_user` |
| Admin client | `libs/fred-core/fred_core/security/keycloak/keycloack_admin_client.py` | parses realm URL |
| KF startup check | `knowledge_flow_backend/application_context.py` `_log_config_summary` | `split_realm_url()` failure **raises `ValueError("Invalid Keycloak URL")`: startup fails** |
| Env-based config | `libs/fred-core/fred_core/security/env_config.py` | builds `UserSecurity`/`M2MSecurity` from `KEYCLOAK_*` variables only |
| Frontend construction | `apps/frontend/src/security/KeycloakService.ts` `createKeycloakInstance`, `apps/frontend/src/common/config.tsx` | `parseKeycloakUrl()` throws on a non-realm URL; realm-mode `keycloak-js` |
| Frontend identity | `KeycloakService.ts` `GetUserId` → `personalTeamId()` in `useChatSse.ts`, `usePipelineRun.ts`, `templateDownload.ts`, `TeamResourcesPage.tsx`, `AuthContext.tsx` | browser user id = access-token `sub`; must equal the backend uid (`personal-<uid>`) |
| Frontend roles | `KeycloakService.ts` `GetUserRoles` / `GetRealmRoles` → `useUserCapabilities.ts` (`admin` debug), `AuthContext.tsx`, `UserSettingsPage.tsx` | `resource_access.<client>.roles`, `realm_access.roles` |
| Self-test probe | `apps/frontend/src/rework/features/pipeline/keycloakDirectGrant.ts` | Keycloak password grant |

Naming-only references (`KeycloakUser`, `KeyCloakService`, `KEYCLOAK_*_CLIENT_SECRET` variable names, docstrings, the `keycloak_user` parameter names) carry no behavior and are left unchanged. The Keycloak-only CLIs (`fred_core/cli/auth.py`, `control_plane_backend/cli`, `fred_runtime/cli`) and `.claude/skills/test-agent-instance` stay Keycloak-only (non-goal).

## Goals / Non-Goals

**Goals**

- A Keycloak deployment with an unchanged configuration behaves exactly as today (same configured URLs, claims and directory; one common OIDC browser lifecycle).
- An `oidc` deployment (Entra ID first) supports login, logout, API calls, workload tokens, delegation, service identities and a usable user directory, using configuration only.
- Inconsistent configurations fail at startup with an explicit message instead of failing silently at request time.
- Agent pods remain stateless: identity normalization needs no database.

**Non-Goals**

See the proposal. In particular: no CLI rework, no SCIM, no Graph lookup, no renames.

## Decisions

### 1. One provider switch, `realm_url` kept as the issuer

`UserSecurity` and `M2MSecurity` gain `provider: Literal["keycloak", "oidc"] = "keycloak"`. The existing `realm_url` field is kept and documented as "Keycloak realm URL or OIDC issuer URL". For Keycloak both values are identical, so no rename is needed and delegation's trusted `issuers` (already derived from `realm_url`) keep working.

*Alternative rejected:* always using discovery, including for Keycloak. It changes startup behavior (extra network call) for existing deployments for no benefit.

### 2. Endpoint resolution lives in `fred-pod`

A new module `libs/fred-pod/fred_pod/security/oidc_endpoints.py` exposes:

```python
@dataclass(frozen=True)
class OidcEndpoints:
    issuer: str
    jwks_uri: str
    token_endpoint: str

def resolve_endpoints(*, provider: str, realm_url: str,
                      jwks_url: str | None = None,
                      token_url: str | None = None,
                      timeout_seconds: float = 5.0) -> OidcEndpoints: ...
```

- `keycloak`: returns the URLs built exactly as today; explicit overrides still win if set.
- `oidc`: fetches `{issuer}/.well-known/openid-configuration` once (synchronous `httpx`, bounded timeout), and checks that the document's `issuer` equals the configured one (trailing slash ignored). Explicit overrides win over discovered values. Any failure raises at startup: the service fails closed.
- Results are cached per `(provider, realm_url, overrides)` in-process.

It lives in `fred-pod` because `M2MAuthConfig` lives there and `fred-pod` must not depend on `fred-core`. `fred-core` imports it.

### 3. Claims are configurable with Keycloak defaults

`UserSecurity` gains:

```yaml
audience: null            # default: client_id (today's behavior)
roles_claim: null         # default: [resource_access, <client_id>, roles]
claims:
  uid: sub
  username: preferred_username
  email: email
  given_name: given_name
  family_name: family_name
jwks_url: null
token_url: null
scope: null               # frontend login scope (Entra: api://<api>/access_as_user)
```

`decode_jwt` reads values through a small helper `_claim_path(payload, path)` (the same traversal as `DelegationConfig.roles_claim_path`). `azp`, falling back to `client_id`, is unchanged. `is_service_agent()` is unchanged: on Entra, the `service_agent` app role, assigned to workload service principals, appears in `roles`, which `roles_claim: [roles]` selects.

### 4. Stateless identity normalization

After reading the identity claim:

- if the value parses as a UUID, it is used unchanged (Keycloak `sub`, Entra `oid`);
- else if `provider == "oidc"`, `uid = str(uuid5(NAMESPACE_URL, f"{issuer}#{value}"))`;
- else (Keycloak), today's behavior is unchanged (a non-UUID uid is accepted and skips the user store, as for the local mock user).

Every service, including agent pods, computes the same uid without shared state, so OpenFGA tuples and the `users` table stay consistent.

*Alternative rejected:* an internal id with a `(issuer, sub) → id` mapping table. Agent pods validate tokens and authorize with OpenFGA on `user.uid` themselves and have no database; a mapping table would break that model.

### 5. Workload tokens: `scope` and a resolved token endpoint

`M2MSecurity` gains `provider`, `scope: str | None` and `token_url: str | None`. `M2MAuthConfig` gains `token_url_override: str | None = None`; its `token_url` property returns the override when set. The three builders (`control_plane_backend/app/context.py`, `fred_runtime/common/outbound_credentials.py`, `fred_sdk/knowledge_base/configuration.py`) pass `scope=m2m.scope` and `token_url_override=resolve_endpoints(...).token_endpoint`.

`oidc.py` exposes `get_token_endpoint()`. `adapters.py` passes it to `user_token_refresher.py`, whose internal parameter becomes the full token URL (the `/protocol/openid-connect/token` suffix moves out). `outbound.py` `ClientCredentialsProvider` accepts an optional `token_url` keyword that takes precedence over `keycloak_base` + `realm`.

Server-side refresh of a person's token remains provider-dependent. Entra refuses it for SPA-issued refresh tokens, so `oidc` deployments on Entra must enable delegation. This is documented, not enforced.

### 6. Startup refusals for inconsistent configurations

`apply_security_profile` (or an adjacent `validate_provider_configuration`, called at the same point) raises `ValueError` when:

- `user.provider == "oidc"` and `delegation.service_accounts_only` is true (its markers are Keycloak-only);
- `user.provider == "oidc"`, delegation is in use, and `delegation.caller_roles_claim` is unset (the default `resource_access.<audience>.roles` would silently reject every delegated call);
- `user.provider == "oidc"` and `user_directory == "keycloak"` (the Admin API does not exist).

### 7. Local directory reuses the Keycloak user representation

`SecurityConfiguration` gains `user_directory: Literal["keycloak", "local"] = "keycloak"`.

- **Guard:** with `local`, `create_keycloak_admin()` returns `KeycloackDisabled()` before parsing the realm URL. Existing fallbacks remain as a safety net, but every read path below is explicitly served from Postgres.
- **Schema:** `UserRow` gains nullable `username`, `email`, `first_name`, `last_name`, `last_seen_at`. One Alembic migration in `apps/control-plane-backend/alembic/versions/` (the table's owner) adds them, plus an index on `lower(username)`.
- **Snapshot write:** on the first authenticated human control-plane request, including `/user` and `/gcu` through `get_current_user_before_gcu`, before any CGU refusal. Retain snapshot behavior for protected API requests without duplicating writes. When `user_directory == "local"`, the principal is a person (not `is_service_agent`, not holding the delegation caller role, not a service-account token) and its uid is a UUID, the user store upserts the snapshot. Writes are throttled in-process per uid (at most once every 10 minutes, bounded LRU) and failures are logged and never fail the request.
- **Store API** (`BaseUserStore` / `PostgresUserStore`): `upsert_identity(...)`, `search_identities(query, limit)`, `list_identities(offset, limit)`, `get_identities(ids)`, `count_identities()`, `find_ids_by_usernames(usernames=None)`, `identity_exists(id)`. Read methods return dicts in the Keycloak Admin API shape (`id`, `username`, `email`, `firstName`, `lastName`). The existing `UserSummary.from_raw_user` and every caller stay unchanged.
- **Service functions** branch once at the top when `user_directory == "local"`:

| Function | Local behavior |
|---|---|
| `control_plane_backend/users/service.py::list_users`, `search_users`, `get_users_by_ids`, `find_user_details_by_id` | store reads; unknown ids keep today's id-only fallback |
| `find_user_subs_bulk`, `find_user_sub_by_username` | `find_ids_by_usernames`; missing usernames stay unresolved exactly as today |
| `user_exists_in_keycloak` | `identity_exists` → real `True`/`False` (unknown id → existing 404) |
| `create_user` | raise new `IdentityManagedByProviderError` → HTTP 409, `{"detail": ..., "reason": "managed_by_identity_provider"}` |
| `users/api.py` delete route | do not obtain the write admin client; keep the root-protection and wildcard checks and the standing ban; skip the identity-provider deletion; succeed |
| `import_export/importer.py` `_provision_bundle_identities` | unchanged code path: its call to `create_user` raises `IdentityManagedByProviderError`, which propagates like `KeycloakM2MUserOperationDisabledError` does today, so the import fails closed before any authorization write, and the task error names the unresolved usernames |
| `teams/service.py` user count | `count_identities` |
| `knowledge_flow_backend/features/users/users_service.py::list_users`, `get_users_by_ids` | store reads |

Local username resolution must never collapse distinct IDs sharing the same exact username into one dictionary entry. Raise a bounded `ambiguous_username` error naming the colliding usernames before constructing the mapping; never select by row order, last-seen timestamp or insertion order. Preserve existing exact-name/case behavior and unique/missing-name results. The import supplies its referenced usernames to the existing bulk prefetch, before its transaction opens, so an unrelated directory collision does not block that bundle and a requested collision aborts before SQL or OpenFGA writes. Keycloak resolution stays unchanged. Identity upserts continue accepting snapshots; do not add a unique constraint, delete rows or guess which identity currently owns a name. Once authoritative profile refreshes remove the collision, resolution works again. This checks observed snapshot ambiguity; it does not establish current IdP ownership for a stale but unique name.

Local suspension uses the existing account-status model independently of delegation. An enforced OpenFGA engine requires active accounts when either delegation is in use or `user_directory == "local"`. Each service validates and installs that engine at startup, then checks authenticated subjects even when both delegation switches are off. Existing Keycloak-directory behavior and delegation checks remain unchanged. A local delete refuses with HTTP 403 `account_suspension_disabled` when account-status enforcement is disabled; it never returns a successful no-op. Model validation failure stops startup, and unavailable request-time checks fail closed. Keep root/wildcard protection, memberships, snapshots and provider accounts unchanged.

*Alternative rejected:* a `UserDirectory` interface with two implementations and a refactor of every caller. It is cleaner in the abstract, but it touches far more Keycloak code for the same behavior; the one-branch approach keeps the Keycloak path untouched.

### 8. Frontend: one OIDC browser lifecycle behind `KeyCloakService`

`/frontend/config` `user_auth` supplies `provider`, `scope`, `user_directory`, `uid_claim` and `roles_claim`. The public `KeyCloakService` facade and its callers remain unchanged.

- Both `keycloak` and `oidc` use the existing `OidcBrowserSession` / `oidc-client-ts` implementation. Remove the alternate `keycloak-js` login/refresh/logout path and its dependency once remaining uses are removed. Keep Keycloak endpoint/claim defaults and explicit directory/admin features.
- For every provider, create an `oidc-client-ts` `UserManager` from the configured issuer and UI client id. Use Authorization Code with PKCE S256, browser redirect callback handling and session storage. Request `openid profile offline_access` plus the configured API scope. Keep the access token (not the ID token) as the API bearer. On page reload, restore the validated `User`; on token expiry/401, use `signinSilent()` (refresh token where available, silent iframe otherwise) with the existing timeout and single-flight behavior. A missing/failed session fails closed and re-enters the provider sign-in flow. Logout clears Fred's persisted bearer and calls `signoutRedirect()` with a registered post-logout URI. The callback handles sign-out state without starting a second login before the provider returns.
- Classify renewal errors by the structured OAuth/OIDC error code emitted by `oidc-client-ts`, never by message substrings or HTTP status alone. `invalid_grant`, `login_required`, `interaction_required`, `consent_required` and `account_selection_required` end the current Fred browser session: invalidate in-memory access/refresh tokens and claims immediately, advance the generation, and remove the persisted OIDC user before refresh callers complete. A failed cleanup must not expose the old in-memory tokens. Network errors, timeouts, `server_error` and `temporarily_unavailable` keep an unexpired bearer available and allow retry. Keep the boolean facade, single-flight behavior and existing sign-in/sign-out flow. Late results must not resurrect an invalidated session or invalidate a newer generation. Serialize session-local storage/timer reconciliation using the currently owned user, because the SDK writes and loads responses before the generation check.
- The OIDC adapter maps access-token claims to the existing getters. `GetKeycloakRealmConfig()` returns `null` in OIDC mode. The password probe requires an explicit Keycloak realm configuration; the credential-expiry scenario works for either provider. No OIDC callback may replay a token after logout.

The former `keycloak-js` `oidcProvider` spike failed at the API precondition: the installed 25.0.6 types and implementation have no such option. The developer authorized using `oidc-client-ts` and, on 2026-09-29, unifying the Keycloak browser path into it. Live Entra validation still requires tenant credentials; mock OIDC covers the browser flow locally.

### 8b. Frontend identity and roles match the backends

The browser computes personal-space ids as `personal-<uid>`, so its uid must equal the backend's (decision 4). `/frontend/config` `user_auth` also exposes `uid_claim` and `roles_claim` (from `security.user.claims.uid` and `security.user.roles_claim`).

- `GetUserId()`: reads `tokenParsed[uid_claim]` (default `sub`). With `provider === "oidc"` and a non-UUID value, it returns `v5(`${realm_url}#${value}`, v5.URL)` from the already-installed `uuid` package, which is byte-identical to Python's `uuid5(NAMESPACE_URL, …)`. The issuer string must be normalized exactly as in the backend (trailing slash stripped).
- `GetUserRoles()`: reads the configured `roles_claim` path when set, else today's `resource_access.<clientId>.roles`. `GetRealmRoles()` is unchanged (empty on other providers).
- Display helpers (`preferred_username`, `name`, `given_name`, `email`) are unchanged. The Entra recipe adds the optional claims so they are present.

A shared test vector (issuer, value, expected uuid) is asserted on both sides.

### 8c. Environment-based first-party configuration

`security_configuration_from_env` (`env_config.py`) reads optional `OIDC_PROVIDER`, `OIDC_AUDIENCE`, `OIDC_SCOPE`, `OIDC_ROLES_CLAIM` (comma-separated path), `OIDC_UID_CLAIM`, `OIDC_M2M_SCOPE` and `FRED_USER_DIRECTORY`. Absent variables keep today's values. Existing `KEYCLOAK_*` variable names are kept; `KEYCLOAK_REALM_URL` is documented as "realm URL or OIDC issuer".

### 9. Token lifetime ceiling

`FRED_JWT_MAX_LIFETIME_SECONDS` stays an environment variable (default 3600). The Entra recipe sets it to 5400, because Entra access tokens live 60–90 minutes. No code change.

### 10. Local test bench in `fred-deployment-factory`

Testing uses the sibling `fred-deployment-factory` repository on its branch matching `test-23-09`, which already provisions the `fred-delegation` client and role. Additions are opt-in Make targets. `make docker-up` is unchanged.

- **`make keycloak-generic-oidc`** (`docker/keycloak/generic-oidc-profile.sh`, reusing the helpers of `keycloak-post-install.sh`): creates a `fred-api` client with no login flows and the roles `service_agent` and `delegation_caller`; creates a client scope `fred-api-shape` with a client-role mapper (`claim.name=roles`, flat, multivalued, access token) and an audience mapper (`fred-api`); adds it as a default scope to `app`, `agentic`, `knowledge-flow`, `control-plane` and `fred-evaluation-worker`; grants `fred-api/service_agent` to the four backend service accounts and `fred-api/delegation_caller` to `agentic`. Option `STRICT=1` detaches the `roles` scope from those clients (no `resource_access` left) and removes the `realm-management` roles from the service accounts, so any leftover Admin API call or Keycloak-claim read fails loudly. `make keycloak-generic-oidc-revert` undoes it.
- **`make mock-oidc-up` / `mock-oidc-down`** (`docker/docker-compose-mock-oidc.yml`): `ghcr.io/navikt/mock-oauth2-server` on port 8090, issuer `http://localhost:8090/fred`, interactive login, 5400-second tokens, per-client claim mappings (`aud: fred-api`, `roles`, `azp`).
- **`local-testing/scripts/warm-local-directory.sh`**: reads the demo users from `fred`'s `users.json` (same discovery as `seed-keycloak-users.sh`), obtains a password-grant token for each on the `app` client, and calls one authenticated control-plane endpoint so each person is recorded before import.
- **Example overlays** in `fred`: `apps/*/config/overlays/configuration_generic_oidc.example.yaml` and `apps/*/config/overlays/configuration_mock_oidc.example.yaml`, holding only the `security` differences.
- `docs/LOCAL-DEVELOPMENT.md` (factory) gains an "Identity provider portability" section with the four levels: Keycloak baseline, Keycloak in generic shape, mock OIDC with Keycloak stopped, real Entra tenant.

The local configuration preparation command derives full host-run YAMLs for
Keycloak, generic OIDC and the mock from the canonical production files and
existing security overlays. Generated files live outside tracked baselines and
are schema-validated before publication. OIDC launch commands disable stale
local delegation files and set the required mock token lifetime; the baseline
retains its usual environment. Entra uses the existing Helm example with the
customer registrations.

## Risks / Trade-offs

- **Discovery at startup adds a network dependency** for `oidc` deployments. It is bounded and fails closed with an explicit message.
- **`uuid5` identities are provider-bound.** Moving a deployment from one issuer to another changes uids. Out of scope; documented.
- **Local directory completeness.** Only people who signed in at least once are searchable, and suspended people still appear in pickers. Acceptable for this change; SCIM or Graph can be added later.
- **Snapshot staleness.** Name and email changes appear after the next throttled write (≤10 minutes after activity).
- **Grant trust model** is unchanged from delegation: any workload holding `delegation_caller` can name any person, bounded by that person's permissions. The Entra recipe restricts the app role to the runtime and first-party apps.
- **Browser OIDC compatibility** depends on the provider allowing the configured redirect and post-logout URIs, refresh-token or silent renew policy, and CORS on discovery/token endpoints; test with the mock and then a real Entra tenant.
- **Import before first sign-in.** In `local` mode the demo import fails closed until every named user has signed in once. Locally the warm-up script covers it; at a customer, imports are run after users' first sign-in.
- **Browser/backend uid drift.** A normalization mismatch would silently point people at another personal space. It is mitigated by the shared test vector and by the level-3 bench (non-UUID `sub`).

## Migration Plan

1. Deploy the code with no configuration change: Keycloak deployments are unaffected. The Alembic migration only adds nullable columns and an index.
2. For an `oidc` deployment: create the provider objects (see `IDENTITY-PROVIDERS.md`), set `provider: oidc`, `user_directory: local`, delegation switches, `caller_roles_claim`, `audience` and `scope`, and `FRED_JWT_MAX_LIFETIME_SECONDS` where needed.
3. Rollback: revert the configuration. The added columns are ignored by older code.

## Open Questions

- Should `local` mode filter suspended people from search results (requires an OpenFGA standing check per result)?
- Should the snapshot also be written in `keycloak` mode, to prepare a later move to `local` without a Keycloak export?

### Follow-up acceptance boundary (2026-09-29)

A valid human bearer may create/update a local profile before CGU acceptance.
The write MUST preserve the accepted version and suspension status. It MUST NOT
create memberships or permissions. Invalid/anonymous requests, workload callers
and delegated asserted persons do not create profiles through this mechanism.
Reuse the existing upsert, throttle and failure logging; do not add a second
identity store. A failed snapshot must never bypass the CGU gate.
