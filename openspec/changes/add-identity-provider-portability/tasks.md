## 0. Preconditions and validation spike

Work on a branch created from `test-23-09` (it contains `add-delegated-agent-execution`). Read `proposal.md` and `design.md` first. **Hard rule for every task: with no new setting configured, behavior, URLs, claims and responses must stay identical to today.** Do not rename existing symbols, settings or files.

- [x] 0.1 Frontend API spike: the installed `keycloak-js` 25.0.6 has no `oidcProvider` constructor option in types or implementation, so this construction cannot compile. The developer authorized the `oidc-client-ts` path in this change. Live Entra validation moves to 10.5; mock-browser validation is required in 7.6 and 10.4.
Spike result (2026-09-27): the installed `keycloak-js` 25.0.6 API and source have no `oidcProvider` constructor option. On 2026-09-27 the developer requested a spec revision to support changing OIDC providers, authorizing the `oidc-client-ts` browser path. A real Entra tenant is still needed for 10.5.

- [x] 0.2 Confirm the baseline: run `make test` and `make code-quality` on the unmodified branch and record failures that already exist, so they are not attributed to this change. Both commands stopped in `libs/fred-pod` before checks ran: Python 3.14 could not create `.venv` because `ensurepip` is unavailable (`python3.14-venv` missing).

## 1. Configuration models (`libs/fred-pod`)

- [x] 1.1 In `fred_pod/security/structure.py`, add to `UserSecurity`: `provider: Literal["keycloak","oidc"] = "keycloak"`, `audience: str | None = None`, `scope: str | None = None`, `jwks_url: AnyHttpUrl | None = None`, `token_url: AnyHttpUrl | None = None`, `roles_claim: list[str] | None = None`, and `claims: UserClaims = UserClaims()` where `UserClaims` has `uid="sub"`, `username="preferred_username"`, `email="email"`, `given_name="given_name"`, `family_name="family_name"`. Document `realm_url` as "Keycloak realm URL or OIDC issuer URL".
- [x] 1.2 Add to `M2MSecurity`: `provider` (same literal, default `keycloak`), `scope: str | None = None`, `token_url: AnyHttpUrl | None = None`.
- [x] 1.3 Add to `SecurityConfiguration`: `user_directory: Literal["keycloak","local"] = "keycloak"`.
- [x] 1.4 Regenerate the configuration JSON schemas and the Helm `values.schema.json` with the repository's existing generators. Add the new keys, commented out, to `deploy/charts/fred/values.yaml`.
- [x] 1.5 `libs/fred-core/fred_core/security/env_config.py`: read optional `OIDC_PROVIDER`, `OIDC_AUDIENCE`, `OIDC_SCOPE`, `OIDC_ROLES_CLAIM` (comma-separated path), `OIDC_UID_CLAIM`, `OIDC_M2M_SCOPE` and `FRED_USER_DIRECTORY` into the models above (design §8c). Keep every `KEYCLOAK_*` name and the existing `KEYCLOAK_M2M_AUDIENCE` refusal.
- [x] 1.6 Tests: an old configuration file parses to the defaults above; invalid literals are rejected; `security_configuration_from_env` with only today's variables equals today's result, and with the new variables sets each field.

## 2. Endpoint resolution (`libs/fred-pod`)

- [x] 2.1 Create `fred_pod/security/oidc_endpoints.py` with `OidcEndpoints(issuer, jwks_uri, token_endpoint)` and `resolve_endpoints(provider, realm_url, jwks_url=None, token_url=None, timeout_seconds=5.0)` as specified in design §2: Keycloak URLs are built exactly as today; `oidc` uses one synchronous discovery request, checks that the issuer matches (trailing slash ignored), lets explicit overrides win, caches in-process and raises `RuntimeError` with a clear message on any failure.
- [x] 2.2 Export it from `fred_pod/security/__init__.py`.
- [x] 2.3 Tests (mock HTTP, no network): Keycloak URL construction is unchanged; discovery succeeds; issuer mismatch fails; timeout or non-200 response fails; overrides win; the second call hits the cache.

## 3. Token validation (`libs/fred-core/fred_core/security/oidc.py`)

- [x] 3.1 `initialize_user_security`: resolve endpoints through `resolve_endpoints`, set `KEYCLOAK_JWKS_URL` from `jwks_uri`, store the issuer and token endpoint in module globals, and call `split_realm_url` for the log line only when `provider == "keycloak"`.
- [x] 3.2 Add `get_token_endpoint() -> str` next to `get_keycloak_url()` and export it from `fred_core/__init__.py`.
- [x] 3.3 `decode_jwt`: the expected audience becomes `[config.audience or KEYCLOAK_CLIENT_ID]` (plus the delegation audience, unchanged), in both the soft check and the strict check.
- [x] 3.4 `decode_jwt`: read the username, email, given name and family name through the configured claim names. Read roles through `roles_claim` when set, else `resource_access.<client_id>.roles` (today's path). Add a small `_claim_path(payload, path)` helper.
- [x] 3.5 `decode_jwt`: read the identity from `claims.uid`. If the value is not a UUID and `provider == "oidc"`, set `uid = str(uuid5(NAMESPACE_URL, f"{issuer}#{value}"))`. Keycloak behavior is unchanged.
- [x] 3.6 Tests, following the existing `fred_core/tests/security/test_oidc_*.py` style (locally generated RSA key, JWKS served by a mock): Keycloak token regression (identical `KeycloakUser`); Entra-shaped v2 token (`oid`, `roles`, `azp`, `aud` = API GUID) with `claims.uid: oid`, `roles_claim: [roles]`, `audience` set; `is_service_agent` true for `roles: [service_agent]`; `uuid5` determinism for a non-UUID `sub`; wrong audience rejected in strict mode.

## 4. Workload and refresh token endpoints

- [x] 4.1 `fred_pod/security/backend_to_backend_auth.py`: add `token_url_override: str | None = None` to `M2MAuthConfig`. `token_url` returns the override when set, else today's value.
- [x] 4.2 Pass `scope=m2m.scope` and `token_url_override=<resolved token_endpoint>` in the three builders: `apps/control-plane-backend/control_plane_backend/app/context.py`, `libs/fred-runtime/fred_runtime/common/outbound_credentials.py`, `libs/fred-sdk/fred_sdk/knowledge_base/configuration.py`. Resolve with `resolve_endpoints(provider=m2m.provider, realm_url=m2m.realm_url, token_url=m2m.token_url)`.
- [x] 4.2b Initialize the control-plane OIDC workload provider at container startup, before request or worker handling, so synchronous discovery never occurs on its lazy bearer path. Test startup failure and provider reuse.
- [x] 4.3 `libs/fred-runtime/fred_runtime/runtime_support/user_token_refresher.py`: take the full token URL instead of the realm URL; move the `/protocol/openid-connect/token` suffix out. In `integrations/v2_runtime/adapters.py`, pass `get_token_endpoint()` instead of `get_keycloak_url()`. Keep `_identity_digest` stable by digesting the token URL.
- [x] 4.4 `libs/fred-core/fred_core/security/outbound.py`: `ClientCredentialsProvider.__init__` accepts an optional keyword `token_url` that takes precedence over `keycloak_base` + `realm`. Existing callers are unchanged.
- [x] 4.5 Tests: the token URL and form (including `scope`) sent by `M2MTokenProvider` for Keycloak (unchanged) and for `oidc`; the refresher posts to the given URL; `ClientCredentialsProvider` honors `token_url`.

## 5. Startup validation

- [x] 5.1 Add `validate_provider_configuration(config: SecurityConfiguration)` in `oidc.py` and call it wherever `apply_security_profile` is called (control plane, knowledge flow, runtime). It raises `ValueError` for the three combinations in design §6, with actionable messages.
- [x] 5.2 `apps/knowledge-flow-backend/knowledge_flow_backend/application_context.py` `_log_config_summary`: today a `split_realm_url` failure **raises `ValueError("Invalid Keycloak URL")` and stops startup**. When `provider == "oidc"`, skip the realm parsing and log the issuer instead. Keep the check, and its failure, when `provider == "keycloak"`. Keep the `KEYCLOAK_KNOWLEDGE_FLOW_CLIENT_SECRET` check unchanged (the variable name is only a name).
- [x] 5.3 Tests: each refused combination fails; valid `oidc` + `local` + `caller_roles_claim` passes; Keycloak defaults pass; Knowledge Flow starts with an Entra-style issuer in `oidc` mode and still refuses a malformed realm URL in `keycloak` mode.

## 6. Local user directory

- [x] 6.1 `libs/fred-core/fred_core/users/user_models.py`: add nullable `username`, `email`, `first_name`, `last_name` (`String`) and `last_seen_at` (`DateTime(timezone=True)`) to `UserRow`.
- [x] 6.2 Add one Alembic migration in `apps/control-plane-backend/alembic/versions/` adding those columns and an index on `lower(username)`, with a working downgrade. Check that knowledge flow's Alembic tree and backfill scripts are not affected. Run `make db-check-combined-sqlite`.
- [x] 6.3 `BaseUserStore` / `PostgresUserStore`: add `upsert_identity`, `search_identities(query, limit)` (case-insensitive match on username, email, first and last name), `list_identities(offset, limit)`, `get_identities(ids)`, `count_identities()`, `find_ids_by_usernames(usernames | None)`, `identity_exists(id)`. Read methods return dicts shaped like Keycloak Admin API users: `{"id","username","email","firstName","lastName"}`.
- [x] 6.4 `libs/fred-core/fred_core/security/keycloak/keycloack_admin_client.py`: accept the `SecurityConfiguration` (or a `user_directory` argument) and return `KeycloackDisabled()` before any realm parsing when `user_directory == "local"`. Update the callers' arguments.
- [x] 6.5 Snapshot write in `oidc.py` `get_current_user` and `get_current_user_or_service`: when `user_directory == "local"`, the principal is a person (not `is_service_agent`, no delegation caller role, not a service-account token, username present) and the uid is a UUID, call `upsert_identity`. Throttle per uid (10 minutes, bounded LRU). Catch and log failures without raising. Exclude the no-security mock user.
- [x] 6.6 `apps/control-plane-backend/control_plane_backend/users/service.py`: add one `if user_directory == "local":` branch at the top of `list_users`, `search_users`, `get_users_by_ids`, `find_user_details_by_id`, `find_user_subs_bulk`, `find_user_sub_by_username` and `user_exists_in_keycloak`, serving results from the store and reusing `UserSummary.from_raw_user`. Keep the existing unresolved and id-only fallback semantics.
- [x] 6.7 `create_user`: in `local` mode raise a new `IdentityManagedByProviderError` (in `users/schemas.py`), mapped in `users/api.py` `register_exception_handlers` to HTTP 409 `{"detail": ..., "reason": "managed_by_identity_provider"}`.
- [x] 6.8 `users/api.py` delete route: today it calls `_get_keycloak_admin_for_user_operations(deps)` **before** the standing ban, which raises when the Admin API is disabled. In `local` mode, do not obtain the admin client. Keep the root-protection and wildcard checks and `rebac.remove_user_standing(user_id)`, skip `delete_user_from_service`, and return success. The Keycloak mode ordering stays unchanged.
- [x] 6.8b `import_export/importer.py`: verify that `_provision_bundle_identities` → `create_user` in `local` mode raises `IdentityManagedByProviderError` and that it propagates exactly as `KeycloakM2MUserOperationDisabledError` does (import fails closed before any authorization write). Make the task error name the unresolved usernames and the `managed_by_identity_provider` reason. Update the docstrings that say the import "creates a Keycloak user" to mention the local-mode refusal.
- [x] 6.9 `apps/control-plane-backend/control_plane_backend/teams/service.py`: the user count uses `count_identities()` in `local` mode.
- [x] 6.10 `apps/knowledge-flow-backend/knowledge_flow_backend/features/users/users_service.py`: `list_users` and `get_users_by_ids` read the store in `local` mode (same permission check as today).
- [x] 6.11 Tests: snapshot written once per throttle window and never for service identities; the store search matches by each field; each service function in `local` mode (including `users.json` import resolved and unresolved, a bundle entry with `password` for an unknown user failing closed with no authorization write, platform-role grant 404 for an unknown id, create 409, delete suspends without an IdP call and keeps root protection); the Keycloak mode path is unchanged (existing tests pass untouched).

## 7. Frontend

- [x] 7.1 Control plane `/frontend/config`: add `provider`, `scope`, `user_directory`, `uid_claim` and `roles_claim` to `user_auth` (from `security.user.provider`, `security.user.scope`, `security.user_directory`, `security.user.claims.uid`, `security.user.roles_claim`). Regenerate `controlPlaneOpenApi.ts`.
- [x] 7.2 `apps/frontend/src/common/config.tsx`: pass `provider`, `scope`, `user_directory`, `uid_claim`, `roles_claim` and the frontend base URL to `createKeycloakInstance`, retaining Keycloak defaults when fields are omitted.
- [x] 7.3 Add `oidc-client-ts` and a browser adapter behind `KeyCloakService` for `provider === "oidc"`: issuer discovery, Authorization Code + PKCE S256, redirect callback, session restore, API access token, bounded single-flight silent refresh, failed-session handling, provider sign-out and sign-out callback. Keep the Keycloak branch untouched. `GetKeycloakRealmConfig()` returns `null` in OIDC mode.
- [x] 7.4 Check that `SelfTestPage.tsx` / `useAuthzProbeRun.ts` hide the "test another profile" probe when `GetKeycloakRealmConfig()` is `null`, and that `credentialExpiryScenario.ts` skips. Add the guard if either does not already.
- [x] 7.5 Hide the "create user" action in user administration when `user_directory === "local"`. No UI action currently calls the generated create-user mutation, so there is nothing to hide; the API rejects creation in local mode (6.7).
- [x] 7.5b `KeycloakService.ts` `GetUserId()`: read `tokenParsed[uid_claim]` (default `sub`). With `provider === "oidc"` and a non-UUID value, return `v5(`${issuer}#${value}`, v5.URL)` using the installed `uuid` package, with the issuer normalized exactly as in the backend (trailing slash stripped). Callers (`useChatSse.ts`, `usePipelineRun.ts`, `templateDownload.ts`, `TeamResourcesPage.tsx`, `AuthContext.tsx`) stay unchanged.
- [x] 7.5c `KeycloakService.ts` `GetUserRoles()`: read the configured `roles_claim` path when set, else today's `resource_access.<clientId>.roles`. `GetRealmRoles()` and the display helpers stay unchanged.
- [x] 7.6 Tests (Vitest, existing `KeycloakService.test.ts` style): Keycloak construction is unchanged; `oidc` uses `UserManager` with issuer, PKCE and API scope, never calls `parseKeycloakUrl`, and handles login callback, reload, refresh, logout and late refresh after logout; the self-test probe is hidden in `oidc` mode; `GetUserId` returns the claim value for a UUID and the `uuid5` value otherwise; `GetUserRoles` honors `roles_claim`.
- [x] 7.7 Shared test vector: add one `(issuer, value, expected_uuid)` fixture asserted by both a Python test (`oidc.py` normalization) and a Vitest test (`GetUserId`), so browser and backend cannot drift.

## 8. Documentation and deployment

- [x] 8.1 New `docs/swift/platform/IDENTITY-PROVIDERS.md`: the settings table (defaults = Keycloak); a complete Microsoft Entra ID recipe; a generic OIDC checklist; known limitations (directory contains only people who signed in, `uuid5` ids tied to the issuer, server-side person-token refresh depends on the provider).
- [x] 8.2 The Entra recipe must state, as prerequisites:
  - app registrations: **Fred UI** (SPA platform, redirect and post-logout URLs, delegated permission `access_as_user`); **Fred API** (App ID URI `api://fred-api`, scope `access_as_user`, `requestedAccessTokenVersion: 2`, app roles `service_agent` and `delegation_caller` with allowed member type Application, optional claims `email`, `given_name`, `family_name`); one confidential app each for **runtime**, **knowledge flow** and **control plane** with the matching app roles granted;
  - Fred settings: `realm_url: https://login.microsoftonline.com/<tid>/v2.0`, `provider: oidc`, `client_id: <UI client id>`, `audience: <API client id GUID>`, `scope: api://fred-api/access_as_user`, `claims.uid: oid`, `roles_claim: [roles]`, `user_directory: local`, `m2m.scope: api://fred-api/.default`, delegation `act_for_people` / `accept_delegated_calls` on, `caller_roles_claim: [roles]`, `audience: <API client id GUID>`, `service_accounts_only: false`;
  - environment: `FRED_JWT_MAX_LIFETIME_SECONDS=5400`.
- [x] 8.3 `docs/swift/platform/KEYCLOAK.md`: add one paragraph pointing to `IDENTITY-PROVIDERS.md` and noting that Keycloak remains the default.
- [x] 8.4 Add a commented `values-entra.example.yaml` next to the Helm values. It is an example only; customer values live in the customer's deployment repository.

## 9. Local test bench (`fred-deployment-factory`, sibling repository)

Work on the factory branch matching `test-23-09` (it provisions `fred-delegation`). Reuse the helpers of `docker/keycloak/keycloak-post-install.sh` (`kc`, `client_uuid`, `ensure_client_role`, `ensure_user_client_role`, `ensure_audience_mapper`). Every addition is opt-in; `make docker-up` must stay byte-for-byte identical in effect.

- [x] 9.1 `docker/keycloak/generic-oidc-profile.sh` + Make targets `keycloak-generic-oidc` / `keycloak-generic-oidc-revert` (design §10): client `fred-api` (no login flows) with roles `service_agent` and `delegation_caller`; client scope `fred-api-shape` with an `oidc-usermodel-client-role-mapper` (`usermodel.clientRoleMapping.clientId=fred-api`, `claim.name=roles`, `multivalued=true`, access token only) and an `oidc-audience-mapper` (`included.client.audience=fred-api`); scope added as default to `app`, `agentic`, `knowledge-flow`, `control-plane`, `fred-evaluation-worker`; `fred-api/service_agent` granted to the four backend service accounts and `fred-api/delegation_caller` to `agentic`. `STRICT=1` also detaches the `roles` default scope from those clients and removes `realm-management` `query-users`/`view-users`/`manage-users` from the service accounts. The script is idempotent; the revert restores the baseline.
- [x] 9.2 `docker/docker-compose-mock-oidc.yml` + Make targets `mock-oidc-up` / `mock-oidc-down`: `ghcr.io/navikt/mock-oauth2-server` (pin a version) on port 8090, issuer id `fred`, `interactiveLogin: true`, `tokenExpiry: 5400`, request mappings per `client_id` for `agentic`, `knowledge-flow`, `control-plane` (`aud: fred-api`, `azp`, `roles` with `service_agent`, plus `delegation_caller` for `agentic`) and a default mapping (`aud: fred-api`). Check the configuration keys against the image's README for the pinned version.
- [x] 9.3 `local-testing/scripts/warm-local-directory.sh`: discover the demo users exactly as `local-testing/demo/seed-keycloak-users.sh` does (sibling `fred` checkout, `SWIFT_SRC` override), obtain a password-grant token for each on the `app` client, and call one authenticated control-plane GET so the snapshot is written. Print a per-user OK/FAIL summary and exit non-zero on any failure.
- [x] 9.4 In sibling `fred-deployment-factory`: keep `examples/identity-providers/<backend>/configuration_generic_oidc.example.yaml` and `configuration_mock_oidc.example.yaml`, each holding only the `security` block differences (`provider: oidc`, `audience: fred-api`, `roles_claim: [roles]`, `user_directory: local`, delegation `caller_roles_claim: [roles]`, `audience: fred-api`, `service_accounts_only: false`; the mock variant with issuer `http://localhost:8090/fred`). Document how to select them through the existing `CONFIG_FILE` mechanism without editing tracked YAML.
- [x] 9.5 Factory `docs/LOCAL-DEVELOPMENT.md`: add an "Identity provider portability" section describing the four levels and their commands (see section 10). Mention `make checkpoint-save NAME=kc-baseline` / `checkpoint-restore` to switch between levels without reprovisioning.

- [x] 9.6 Provide a local configuration preparation command that merges the existing canonical production configurations and provider overlays, validates each complete YAML against its application schema, and writes launchable Keycloak, generic OIDC and mock OIDC profiles without reading or copying credentials. Document API, runtime, worker and frontend launch commands, local-delegation override handling, and the functional changes. Entra continues to use the existing Helm example, requiring tenant-specific public IDs and credentials.

- [x] 9.7 Add per-backend Entra and ZITADEL configuration examples. Extend the local preparation command to require real Entra public identifiers and generate complete schema-validated configurations; keep the factory as the source of dynamically provisioned ZITADEL configurations and credentials. Document the shorter provider test setup and required environment variables.

## 10. Verification

- [x] 10.1 `make code-quality` and `make test` pass in `fred`, with no new failures compared with 0.2.
- [ ] 10.2 **Level 1, Keycloak baseline.** On the unmodified configuration, run the full `LOCAL-DEVELOPMENT.md` walkthrough (docker-up, setup-env, delegation, run, bootstrap, seed, import, activate capabilities), then `make validation-report` and the UI self-test. Compare with a report captured before the change: identical.
- [ ] 10.3 **Level 2, Keycloak in generic shape.** On a fresh stack or a dedicated checkpoint: `make keycloak-generic-oidc STRICT=1`, select the generic-OIDC overlays, bootstrap, seed the demo users, run `warm-local-directory.sh`, import the demo bundle, activate capabilities, then `make validation-report` and the UI self-test (the password probe must be hidden). Also verify: user search, team member display, create 409, delete suspension, the platform-role grant 404, an import with an unknown `password` entry failing closed, and each startup refusal from 5.1 by breaking the configuration on purpose. Repeat once with `claims.uid: preferred_username` to exercise the `uuid5` path, and check that the personal space opens (browser and backend uid agree).
- [ ] 10.4 **Level 3, non-Keycloak provider.** `make mock-oidc-up`, select the mock overlays, then `docker stop app-keycloak`. Sign in through the mock login page, open the personal space, chat with an agent that reads documents (delegation), search users. Everything must work with Keycloak stopped.
- [ ] 10.5 **Level 4, Entra ID** (free tenant, frontend on `http://localhost:5173`): follow `IDENTITY-PROVIDERS.md` from scratch. Verify login and logout, a token older than 60 minutes still accepted, agent document access through delegation, service identities recognized, directory operations, the personal space (uid `oid`), and the result of spike 0.1.
- [x] 10.6 Review the diff: no renamed symbol, no changed default, no change to the OpenFGA schema or tuples, no new network call in Keycloak mode, and no change to `make docker-up` in the factory.

Verification note (2026-09-27): targeted mock OIDC client-credentials tokens carried issuer `http://localhost:8090/fred`, audience `fred-api`, expected service roles, and 5400-second lifetime. The Keycloak generic profile applied and reverted successfully in normal and `STRICT=1` modes; the mock container was stopped afterward. Root `make code-quality` and `make test` both stopped before checks in `libs/fred-pod` because `uv sync` recreated `.venv` without the expected `.venv/bin/uv` executable.

Migration verification (2026-09-27): `make db-check-combined-sqlite` passed all four Alembic trees, drift checks and downgrades with `CP_UV`, `KF_UV`, `RT_UV` and `WD_UV` pointed to the existing control-plane `uv` executable. This bypassed the repository venv bootstrap path that removed its own `uv` binary.

Verification (2026-09-28): both root commands passed all 16 modules with `UV=/home/thomas/Documents/fred/apps/control-plane-backend/.venv/bin/uv`: `make code-quality` and `make test`. Root tests passed 6194 Python tests, 375 shared-frontend tests and 2853 application-frontend tests (9422 total). The root suite reported 16 skips, including three runtime tests requiring unavailable `fastapi_mcp`; integration tests were excluded by the existing offline targets.

Corrections verified: the local identity snapshot preserves the Keycloak default when a minimal configuration omits `security` (44 delegation, GCU-admission and snapshot regression tests passed); control-plane workload discovery is initialized before request handling (4.2b; six service-token tests passed); runtime JWT fixtures isolate the configured audience, issuer and claims (full runtime: 1417 passed). Control-plane workload discovery runs at startup with a bounded timeout; the identity-write throttle remains process-local, with identity data shared in Postgres. No new LLM or tool call path was introduced.

Levels 10.2–10.5 remain unverified: the complete baseline/generic/mock UI walkthroughs and a real Entra tenant are still required. The requested grouped human review of the commits remains pending. The change is not ready to archive.

Configuration preparation verification (2026-09-28): `/usr/bin/python3 scripts/prepare_identity_provider_configs.py` generated all nine complete files under `/tmp/fred-idp-tests`. JSON-schema and provider-configuration validation passed for each file; baseline values were identical and OIDC profiles preserved non-security values. Ruff and diff whitespace checks passed. No service was started and no complete browser walkthrough was run as part of this configuration-only addition.

## 11. Agreed follow-up: common browser OIDC and pre-CGU profiles (2026-09-29)

Earlier checked tasks document the delivered baseline; they do not imply these
new acceptance criteria are implemented.

- [x] 11.1 Route Keycloak and generic providers through `OidcBrowserSession`; preserve endpoint/claim defaults and the existing `KeyCloakService` facade, remove the alternate browser lifecycle and unused `keycloak-js` dependency.
- [x] 11.2 Verify Keycloak and generic login, PKCE callback, reload, refresh, logout, failed refresh and late callback after logout; preserve user ids, roles and personal-space ids. Keep password probes gated by explicit Keycloak configuration and expiry checks provider-independent.
- [x] 11.3 Reuse local identity upsert on the first authenticated human control-plane request, including `/user` before CGU acceptance; keep workload/delegated exclusions, throttle and failure handling.
- [x] 11.4 Verify a new person who leaves the CGU page still appears in the directory with no acceptance; protected requests remain 403. Verify profile updates preserve acceptance/suspension and invalid/workload tokens create no human row.
- [ ] 11.5 Update current-behavior documentation after implementation and manually verify the pre-CGU profile and common browser flow with Keycloak and a non-Keycloak provider.

Follow-up verification (2026-09-29): common OIDC, self-test and expiry checks
passed (72 frontend tests); TypeScript `tsc --noEmit` passed. The shared browser
suite exercises both provider settings, callback/reload/refresh/logout, timeout
and late refresh, concurrent callers and preserved Keycloak defaults. Snapshot,
CGU admission and local-store checks passed (16 backend tests), including missing
acceptance, invalid credentials, service/delegated exclusions and preservation
of accepted CGU on profile updates. Suspension remains in OpenFGA, which the
identity upsert does not modify. Targeted Ruff and whitespace checks passed.
Task 11.5 remains pending for manual Keycloak/ZITADEL browser checks. OpenSpec
CLI is unavailable in this environment; the change is not archived.

## 12. Review correction: local suspension without delegation

- [x] 12.1 Enable account-status enforcement for local-directory OpenFGA engines and install/check it independently of delegation; preserve the default Keycloak-directory path.
- [x] 12.2 Refuse local deletion when suspension cannot be enforced; preserve root/wildcard protection and retained memberships, snapshots and provider accounts.
- [x] 12.3 Verify factory configuration, startup model validation, subsequent authenticated admission, unavailable checks and deletion failures with delegation off/on; retain Keycloak regression coverage.
- [x] 12.4 Update the existing provider/migration guides, regenerate the API client if its controller changes, run focused tests and independent read-only review, then root quality once and commit/push this block on the existing issue/PR.

Correction verification (2026-10-05): targeted offline suites passed: core security
121, control-plane deletion/startup 38, Knowledge Flow startup/receiver 25,
runtime admission/receiver 83 with 11 dependency-based skips. Commands used the
existing module virtual environments, `pytest -q -o addopts='' --disable-socket
--allow-unix-socket`, with bounded execution. `make update-control-plane-api`
regenerated OpenAPI and frontend output without a diff. `make migration-check`
and strict OpenSpec validation passed.

Independent read-only author/performance review covered the corrective worktree
delta against `740ebdfa6`, including the Knowledge Flow startup guard and shared
CP/KF/runtime/first-party SDK consumers; no actionable finding remained. The PR
target is `swift` (`22b597663`); this is a focused correction review, not a new
full PR review. Local authentication adds one async, timed, higher-consistency
OpenFGA check per request. No real IdP/OpenFGA/PostgreSQL or load test was run;
other portability findings and UUID canonicalization are excluded. The original
manual provider walkthroughs remain pending; this change is not ready to archive.

Root `make code-quality` passed once across all 16 modules after this slice.
The correction is delivered as a dedicated commit on the existing issue/PR branch.

## 13. Review correction: ambiguous local usernames

- [x] 13.1 Reject exact username collisions between distinct IDs in local store resolution with an explicit bounded error; preserve unique/missing results, casing semantics and non-fatal identity upserts.
- [x] 13.2 Restrict import prefetch to referenced usernames in local mode and propagate ambiguity before SQL/OpenFGA writes; retain Keycloak resolution and full-directory lookup compatibility.
- [x] 13.3 Verify real-store same-name collisions, row-order independence, single/bulk services, stale rename/reuse and recovery; exercise full imports with mixed names and business rows, no persisted SQL/FGA writes on ambiguity and unrelated-collision success.
- [x] 13.4 Update the existing provider/migration guides, obtain independent read-only review, run targeted tests and root quality once, and commit/push this block on the existing issue/PR. No schema migration or provider lookup is added.

Correction verification (2026-10-05): targeted offline suites passed: local
identity store 11, control-plane directory/import 32. Commands used the existing
module environments and `pytest -q -o addopts='' --disable-socket
--allow-unix-socket`. Full `run_import` cases verify mixed unique/ambiguous names,
no bundle SQL/FGA writes on refusal, unrelated-collision success and exact-case
boundaries (`alice` unique alongside ambiguous `Alice`). Root `make code-quality`
passed once across all 16 modules; `make migration-check`, strict OpenSpec
validation and diff whitespace checks passed. No controller or schema changed,
so API generation and a database migration are unnecessary for this slice.

Independent read-only review covered the corrective worktree delta against
`c78a1a564`, including store, single/bulk services, importer, existing task-error
propagation and documentation; no actionable finding remained. It also reviewed
the subsequent case-variant tests with updated passing logs. The PR target stays
`swift` (`22b597663`); this is a focused correction review, not a new full PR
review. Resolution remains one awaited SQL query plus a linear scan. Real
PostgreSQL/IdP/OpenFGA and concurrency were not exercised; collision detection
does not establish current ownership of a stale but unique snapshot. Other
portability findings and pending manual provider tasks remain outside this slice.

## 14. Review correction: definitive browser renewal refusal

- [x] 14.1 Distinguish structured definitive OAuth/OIDC renewal refusals from transient errors in the common browser session; invalidate tokens/claims and remove the stored user without changing the facade or provider sign-out flow.
- [x] 14.2 Verify both providers, real ErrorResponse and OIDC session storage, reload after refusal, coalesced callers, late generation results, cleanup failure, transient retry and expired-token rejection with focused browser-session/consumer tests.
- [x] 14.3 Update existing provider/migration guidance and the product contract, obtain independent read-only review, run focused tests and root quality once, then commit/push this block on the existing issue/PR.

Correction verification (2026-10-05): six targeted frontend suites passed 170
tests: real-SDK browser session/storage, both-provider facade, application
requests, credential-expiry scenario, chat SSE and existing base-query query
serialization. The final real-SDK suite has 18 passing tests. Before correction,
the real session retained access/refresh tokens and the stored user after a real
`ErrorResponse(invalid_grant)`; the same reproduction now exposes none. Tests
cover terminal code classification, reload, concurrent cleanup, storage failure,
transient retry/expiry, timeout, stale success/rejection and late login callback.
Root `make code-quality` passed once across all 16 modules; migration-note,
strict OpenSpec and diff whitespace checks passed. No API/schema changed.

Independent read-only author/performance review covered the corrective worktree
delta against `925a6eb888`, including real SDK storage/events, facade, base
queries, application requests, chat and documentation. It confirmed one P2
timer race when a timed-out renewal and its retry succeed together: the original
user's expiring timer survived despite the accepted user's token being stored.
Serialized session-local storage/timer reconciliation fixes it. The reviewer
replayed the same real-SDK scenario and observed the correct 540-second timer
instead of 240 seconds; the regression also verifies proactive renewal at that
deadline. No actionable finding remained after review of that subsequent delta.
The PR target remains `swift` (`22b597663`); this is a focused correction review,
not a new full PR review. The repair adds local browser storage/event work only,
with no extra provider, backend, LLM or tool request. Real IdP/browser walkthroughs
and load remain unverified. Browser-storage failure cannot guarantee persistent
removal, but current-session tokens remain revoked. Other portability findings,
the excluded import P1 and pending manual tasks remain outside this slice.
