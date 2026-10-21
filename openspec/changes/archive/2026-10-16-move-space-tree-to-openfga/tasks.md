## 1. Model and storage

- [x] 1.1 Add `parent`, `organization` and the effective editor/admin/analyst relations to `openfga/model.fga`; extend `tools/model.py` to `[space]` and `<relation> from parent` only; regenerate `model.json`.
- [x] 1.2 Add migration 0006: drop `space.parent_id`, `space.path` and their constraints, rewrite the space immutability trigger, add the unique organization-name index.
- [x] 1.3 Delete the offline `migrate-authorization` cutover; startup binds a publication or initializes an empty installation only.

## 2. Services

- [x] 2.1 OpenFGA client: parent, organization and children reads, direct roles on one space, link writes in the guarded Write.
- [x] 2.2 Space services: organization lock from links, creation with links, direct parent content role for grants and admin nomination, sibling-name and one-personal-space checks, children from OpenFGA in revocation.
- [x] 2.3 Importer: name resolution through OpenFGA children after organization locks, links published with grants, direct parent-role validation.
- [x] 2.4 HTTP: `/me/spaces` with inheritance and `inherited_roles`; `/authorize/scope` with ancestors and `levels`; team registry organization reads. Regenerate OpenAPI and the frontend manager client.

## 3. Verification

- [x] 3.1 Integration tests: inheritance matrix, personal space isolation, direct parent role despite inheritance, revocation after inheritance, scope levels, inherited listing, rolled-back tuples ignored, sibling names, startup refusal; update wire-count assertions. Mark invariant proofs.
- [x] 3.2 Run manager `make test`, `make test-integration`, `make code-quality`, frontend type check and tests, `make -C docs/architecture check`, `openspec validate --strict`.

## 4. Documentation and close-out

- [x] 4.1 Update arc42 chapters 3, 4, 9 and references A1-A3 in the present tense, the manager README, and add the migration note requiring a local reset.
- [x] 4.2 Record verification evidence here, then one commit on `chore/rust-rebac`; no push. Independent review is handled by the developer's batch.

## Verification evidence (2026-10-15)

- `apps/control-plane`: `make test` (unit, OpenAPI) pass; `make test-integration` 52 passed
  against disposable Postgres 15.12 and OpenFGA v1.15.1; `make code-quality` (clippy
  `-D warnings`, rustfmt, model check) pass.
- New integration tests: `descending_roles_reach_projects_and_member_stays_local`,
  `inherited_access_does_not_replace_parent_membership`,
  `memberships_list_inherited_spaces_with_their_paths`,
  `scope_follows_ancestors_and_levels_only_narrow_it`,
  `sibling_names_are_unique_and_uncommitted_links_are_ignored`,
  `startup_refuses_existing_state_without_a_publication`,
  `hierarchy_reads_have_fixed_request_budgets` (4 Reads for `/me/spaces`, `1 C + 2/1 Read`
  for project/team scope). Updated wire counts: demo import 92 tuple operations,
  batch fixture 549, replay variant 9 Checks / 14 Reads.
- Deleted with the cutover: `offline_cutover_preserves_roles_and_pins_the_published_store`,
  `cutover_rejects_invalid_source_and_replays_ambiguous_copies`,
  `cutover_rejects_changed_permissions_and_inconsistent_hierarchy`.
- Frontend: regenerated `controlPlaneOpenApi.ts`; `tsc --noEmit`, vitest on manager slice,
  Home and sidebar, prettier pass. `make test-provisioning-browser` (real Keycloak and
  Chromium) not run.
- `make -C docs/architecture generate` and `check` pass; `openspec validate --strict` passes;
  `scripts/migration_guides.py check-pr --worktree` validates the migration note.

## Audit close-out (2026-10-16)

The implementation is committed in `098cca415`. The manager/arc42 audit and the
owner correction lot review cover its role, hierarchy, publication and consumer
contracts. Current verification and review dispositions are recorded in the
`add-platform-and-organization-owners` tasks. Its later role model supersedes this
delta's platform-admin/team-manager catalog; both are synchronized in that order.
