## 1. Model and configuration

- [ ] 1.1 `schema.fga`: `organization` gains `member`, `org_admin` and the four team-governance permissions; `platform` loses them and `team_manager`, keeps the `feature_manager` roster; verify with model tests for every scenario of the `tenancy` delta.
- [ ] 1.2 `initial_organization: {id, name}` in the control-plane configuration model, chart values and generated schemas, required; verify startup fails naming the setting when absent.
- [ ] 1.3 Alembic: `organization` table, nullable `teammetadata.organization_id`; verify `alembic heads` shows one head and upgrade/downgrade round-trips.

## 2. Behavior

- [ ] 2.1 Organization registry in `fred_core`; teams and personal rows get their organization at creation; verify with registry tests.
- [ ] 2.2 `teams/service.py` gates check the target team's organization; `POST /teams` creates in the caller's organization; verify the cross-organization scenarios with two organizations seeded in tests.
- [ ] 2.3 First authenticated request writes `member` idempotently, beside the account status check; verify with a test that a second request writes nothing.
- [ ] 2.4 Bootstrap root receives `org_admin` of the initial organization; `org_admin` manages `org_admin`s; `team_manager` removed from role enums and platform-role endpoints; verify granting `team_manager` returns an unknown-role error.
- [ ] 2.5 Startup reconciliation (design Decision 7) under the advisory lock; verify on a step 1 fixture that every former holder keeps every governance action, and that a second run writes nothing.

## 3. Frontend

- [ ] 3.1 Regenerate `controlPlaneOpenApi.ts`; `PlatformRolesPage` and `AdminTeamsPage` show `org_admin` in place of `team_manager`; verify `make code-quality` and `make test` in `apps/frontend`, then a manual check of both pages.

## 4. Close-out

- [ ] 4.1 Docs: `REBAC.md` (organization, `org_admin`, no `team_manager`), dated entry in `CONTROL-PLANE-PRODUCT-CONTRACT.md` §43/§51; migration guide with the required setting (minor version).
- [ ] 4.2 `make code-quality` and `make test` green in every touched project, `fred-performance-reviewer` on the membership write, `/code-review` on the diff.
- [ ] 4.3 Open the cleanup issue of design Decision 6 (delete inert tuples, `organization_id` not null).
