## 1. Platform type

- [ ] 1.1 `schema.fga`: add `platform` with every platform-level relation and permission, repoint `capability`/`app`/`knowledge_base_definition` anchors and class markers to it, leave `organization` with `team` only; verify with model tests asserting each permission's holders are unchanged.
- [ ] 1.2 `fred_core`: one `platform:fred` reference, contextual reverse edges `platform#team`/`platform#personal_team`; repoint every platform-level `ORGANIZATION_ID` use; verify `grep` finds `ORGANIZATION_ID` only on the team edge.
- [ ] 1.3 Startup reconciliation copies platform-level tuples from `organization:fred` to `platform:fred` under the advisory lock; verify with a test that a second run writes nothing.

## 2. Team kind

- [ ] 2.1 Alembic migration: `kind` (default `shared`) and `owner_user_id` on `teammetadata`, downgrade deletes personal rows; verify `alembic heads` shows one head and upgrade/downgrade round-trips.
- [ ] 2.2 Registry: create the personal row where the owner self-grant happens today, expose kind through one `fred_core` function, resolve the `personal` alias from the registry; verify with registry tests, including idempotent creation.
- [ ] 2.3 Startup reconciliation registers existing personal spaces from owner tuples; verify with a test on a pre-upgrade fixture and a second no-op run.
- [ ] 2.4 Team listings and admin views exclude `kind = personal` rows exactly as they excluded synthetic personal spaces; verify existing team-listing tests pass unchanged.
- [ ] 2.5 Add `kind` to the team payload, regenerate `controlPlaneOpenApi.ts`; verify with an API test.

## 3. Remove id inference

- [ ] 3.1 Backends: replace every `is_personal_team_id`/`is_personal_team_ref` call with the registry kind, then delete both functions; verify `grep` finds no `startswith("personal-")` outside the reconciliation in 2.3.
- [ ] 3.2 Runtime: add `team_kind` to the execution context; per site, delete the stale "not a real ReBAC team" distinction or port it to `team_kind`; verify runtime tests and the contract test.
- [ ] 3.3 Frontend: replace `teamId.ts` prefix checks with `team.kind` and delete them; verify `make code-quality` and `make test` in `apps/frontend`.

## 4. Close-out

- [ ] 4.1 Test proving the spec scenario "Identifier no longer decides": a shared team with id `personal-x` is treated as shared end to end.
- [ ] 4.2 Docs: `REBAC.md` (platform object, team kind), dated entries in `CONTROL-PLANE-PRODUCT-CONTRACT.md` and `RUNTIME-EXECUTION-CONTRACT.md §8`; migration note per `MIGRATION-GUIDES.md`.
- [ ] 4.3 `make code-quality` and `make test` green in every touched project, `fred-performance-reviewer` on the runtime and capability-check paths, `/code-review` on the diff.
