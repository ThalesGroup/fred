## 1. Shared configuration and durable state

- [ ] 1.1 Add typed `security.platform_access` configuration in `fred-pod`, whole-value bounded regex validation/matching in `fred-core`, and explicit dependency declaration; verify disabled defaults, invalid enabled settings, nested/string-array attributes and regex timeout cases with focused tests.
- [ ] 1.2 Extend shared users/team models and async stores with internal attribute observations, individual admission exceptions, team flags/link hashes and authoritative settings; verify stable UUIDs, monotonic observations, provenance and preservation of CGU/identity state with store tests.
- [ ] 1.3 Add one additive control-plane Alembic migration after the parent branch's actual head; verify exactly one head, PostgreSQL upgrade/downgrade and SQLite fixture compatibility, including users already present before profile snapshots.
- [ ] 1.4 Initialize admission storage through existing SQL lifecycles in control plane, runtime and Knowledge Flow; verify only control plane creates the authority, missing schemas fail startup and policy/database mismatch cannot silently disable filtering.

## 2. Backend admission and administrative operations

- [ ] 2.1 Add the shared request admission gate after subject/suspension resolution, using live state and effective membership; verify all ordinary HTTP and runtime/query-token resolution callers reject a denied person, including JWT cache hits.
- [ ] 2.2 Apply the same gate to asserted/delegated people with valid current attribute evidence or independent exceptions; verify expiry, obsolete paths, newer-token ordering, pure services and unavailable-authority behavior without changing the delegation envelope.
- [ ] 2.3 Add platform-access state and user exception endpoints under `CAN_MANAGE_PLATFORM`, local-user selection and paginated source projection; verify team managers/admins cannot use them and removing one source preserves other sources.
- [ ] 2.4 Add T0 preview and one-time atomic import with completion state; verify concurrent/retried imports, unknown profile classification, removed entries and later registrations against PostgreSQL fixtures.
- [ ] 2.5 Add authorized-team/Free controls and link generation through platform access administration; verify ordinary team PATCH/import/relation writes cannot set admission flags, personal teams are rejected and activation cannot lock out its acting administrator.
- [ ] 2.6 Integrate team departure/removal, Free removal and deletion with live source withdrawal and link invalidation; verify the next request on another replica is denied with the same JWT and unrelated sources remain effective.

## 3. Narrow denied-user and Free-enrollment flow

- [ ] 3.1 Add own-credential authentication dependencies and a minimal self-status endpoint; verify denied people can record their profile/read their own CGU status without directory/product/personal-team access, and other pre-CGU routes retain admission.
- [ ] 3.2 Add valid-link preview, bounded CGU acceptance and idempotent caller-only enrollment using existing membership writers; verify private/invite-only teams preserve visibility/joining policy, arbitrary identities/roles cannot be selected, and default-team CGU side effects cannot bypass admission.
- [ ] 3.3 Serialize enrollment with Free/link mutations and team deletion using the existing PostgreSQL lock pattern; verify concurrent revocation, retry after membership-write failure, rotation and disable/re-enable never revive old links.

## 4. Frontend and generated contracts

- [ ] 4.1 Expose public `FrontendConfig.supportLink` and minimal self-status models, regenerate the control-plane client with `make update-control-plane-api` from `apps/frontend`, and extend API enhancements; verify generated drift is absent and the existing support-menu consumer resolves the same configured URL.
- [ ] 4.2 Build `/admin/platform-access` with the existing design components, navigation permissions, filtering switch, local-user exceptions, T0 preview/import and team/Free controls; verify English/French strings, pagination/provenance, immutable completed T0 and permission-gated controls in focused component tests.
- [ ] 4.3 Build a standalone denial page and handle only `platform_access_denied` in shared/managed-runtime request paths; verify it renders with failed bootstrap, clears protected shell caches, respects frontend basename and preserves unrelated 401/403/503 handling.
- [ ] 4.4 Build `/join-free/:token` outside the protected shell and retain it through OIDC login, CGU acceptance and successful enrollment; verify valid/invalid links, retry/sign-out, denied login and refreshed admission/bootstrap with focused tests and a browser walkthrough.

## 5. Deployment, verification and close-out

- [ ] 5.1 Add disabled developer YAML examples and canonical `global.platformAccess` Helm values/template wiring, regenerate all affected configuration/chart schemas and validate them; verify all participating backends receive the same policy, disabled defaults stay compatible and conflicting legacy whitelist modes are refused.
- [ ] 5.2 Update `CONTROL-PLANE-PRODUCT-CONTRACT.md`, relevant runtime/security guidance, `KEYCLOAK.md`, `IDENTITY-PROVIDERS.md` and `COMPONENT-UX.md`, and revise this PR's migration note to operational minor impact; verify fields/endpoints and activation/rollback instructions match the implementation without duplicating the capability spec.
- [ ] 5.3 Run integration acceptance with matching, grandfathered, new denied and Free users across direct/delegated calls; verify suspension/CGU, default-team bypass prevention, revocation across replicas, storage outage and legacy-disabled upgrade. Record exact commands and observed results in these tasks or the existing PR.
- [ ] 5.4 At commit/readiness, run root `make code-quality` once for the implementation series, affected offline suites, configuration/chart/migration checks and the required performance review; verify all actionable failures are resolved and document untested deployment boundaries.
- [ ] 5.5 Apply the full branch audit against `feat/use-keycloack-only-as-an-idp` and obtain an independent read-only review of the implementation; record base/head, coverage, findings/dispositions and evidence in the PR, then reconcile artifacts, sync/archive the completed change and push the updated draft stacked PR.
