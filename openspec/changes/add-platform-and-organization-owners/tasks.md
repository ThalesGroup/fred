## 1. Model and roles

- [x] 1.1 Rename the platform `admin` relation to `owner`, remove `team_manager` and `can_create_team`; add space `owner` and `can_own`; regenerate `model.json`.
- [x] 1.2 `PlatformRole::PlatformOwner` (`platform_owner`, import alias `owner`), remove `TeamManager` and `CreateTeam`; add `Role::Owner`.

## 2. Services

- [x] 2.1 Bootstrap grants platform owner; platform owners manage platform roles, last platform owner protected under the platform lock.
- [x] 2.2 Space roles: owner only on organizations and granted by platform owners; organization admins granted by owners or admins; last organization owner protected; team creation without platform delegation.
- [x] 2.3 `create-org` grants owner, admin and member; import requires a declared owner and admin for new organizations and refuses owner below organizations.
- [x] 2.4 Regenerate the OpenAPI and frontend manager client; switch the manager platform-authority hook to `platform_owner`; add owner role labels.

## 3. Verification

- [x] 3.1 Integration tests: platform owner handover and last-owner refusal, organization owner powers and limits, owner refused on teams, team creation by organization admins only, import owner rules; update existing platform-admin and team-manager tests and wire counts. Mark invariant proofs.
- [x] 3.2 Run manager `make test`, `make test-integration`, `make code-quality`, frontend type check and affected tests, `make -C docs/architecture check`, `openspec validate --strict`.

## 4. Documentation and close-out

- [x] 4.1 Update arc42 chapters 2, 3, 4, 9 and A1-A3, the manager README, the demo bundle, and the migration note.
- [ ] 4.2 Record verification evidence, then one commit on `chore/rust-rebac`; no push.

## Verification evidence (2026-10-15)

- `apps/fred-manager`: `make test` pass; `make test-integration` 53 passed against disposable
  Postgres 15.12 and OpenFGA v1.15.1; `make code-quality` pass.
- New or rewritten tests: `organization_owners_name_admins_and_read_nothing`,
  `platform_owners_manage_each_other_and_keep_one`, `teams_are_created_by_organization_admins_only`,
  `revoked_platform_actor_cannot_complete_a_waiting_platform_or_owner_grant`; owner added to the
  permission matrix; HTTP import refuses a team owner and a new organization without owner.
- Wire counts: demo import 28 Checks, 18 Reads, 24 Writes, 90 tuple operations; batch fixture
  317 grants, 550 tuple operations.
- Demo fixture: Alice `platform_owner`, Oscar owner of Demo, `team_manager` removed.
- Frontend: regenerated client; `useManagerPlatformAdmin` checks `platform_owner`; owner labels
  (en, fr); `tsc --noEmit`, vitest on manager slice, provisioning, layouts, Home and app (100 tests),
  prettier pass. `tests/provisioning-browser.mjs` updated (inherited editor role, second owner
  replays); `make test-provisioning-browser` not run (real Keycloak and Chromium).
- `make -C docs/architecture generate` and `check` pass; `openspec validate --strict` passes;
  migration note validated.
