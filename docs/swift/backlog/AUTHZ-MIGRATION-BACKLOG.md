# AUTHZ — Full RBAC → ReBAC migration backlog

Track: `AUTHZ-01` (umbrella) · RFC: [RBAC-TO-REBAC-MIGRATION-RFC](../rfc/RBAC-TO-REBAC-MIGRATION-RFC.md)
Owner: Simon · Status registry: [id-legend.yaml](../data/id-legend.yaml) · PMO: [PMO-BOARD.md](../PMO-BOARD.md)
Execution: GitHub issue #1875

Goal: a single authorization model — **ReBAC only**. Remove all RBAC
(`@authorize`, `authorize_or_raise`, `is_authorized`, `require_admin`); cover every endpoint with ReBAC,
adding only `check_user_permission_or_raise` / `check_user_team_permission_or_raise` / `lookup_user_resources`.
Ownership checks (`require_task_access`, session/checkpoint ownership) are **kept** (not RBAC).

---

## AUTHZ-02 — Org-level schema extension + enums  ✅ DONE
- [x] Add fine-grained permissions to the `organization` type in `schema.fga`
      (`can_read_kpi/logs/metrics/opensearch` → viewer ;
       `can_read_kpi_global`, `can_administer_users`, `can_manage_platform`, `can_run_benchmark` → admin)
- [x] Regenerate `schema.fga.json` (`cd libs/fred-core && make transform-openfga-schema`)
- [x] Add `DocumentPermission.PROCESS` + new `OrganizationPermission` members in `rebac_engine.py`
- [ ] Unit tests for the new org-level permissions (viewer reads, admin manages, no-role denied) — existing 48 security tests pass; dedicated org-perm tests still TODO

## AUTHZ-03 — Endpoint migration (buckets A/B/C)

### Bucket A — instance-scoped (`check_user_permission_or_raise`)
- [x] `knowledge-flow content_service.py` (8 reads) → `DocumentPermission.READ` / `document_uid` (gate via `get_document_metadata` + explicit checks on non-delegating methods)
- [x] `knowledge-flow model/controller.py` umap (zero-authz) → `TagPermission.READ`/`UPDATE` _(feature since removed as dead code — see QUALITY-04)_
- [x] `knowledge-flow scheduler_controller.py` `process-library` → `TagPermission.UPDATE` on `library_tag`
- [ ] `knowledge-flow scheduler_controller.py` `process-documents` → per-file `DocumentPermission.PROCESS` (needs file-model design; still RBAC)
- [ ] `knowledge-flow ingestion_service.py` upload → `TagPermission.UPDATE` per destination tag
- [ ] `control-plane evaluations/api.py` (zero-authz) → team `CAN_READ`/`CAN_UPDATE_RESOURCES`
      (load `team_id` from the campaign for `campaign_id`-only routes)
- [ ] `knowledge-flow audio_transcription_controller.py` → scope per RFC D3

### Bucket B — collections/search (`lookup_user_resources`)
- [ ] Drop residual `@authorize` on already-ReBAC services (metadata, tabular, vector_search.search, tag list_all_tags)
- [ ] Wire lookup-filtering: `resources list_resources_by_kind`, runtime `list_agents`, `statistic /stat/*`

### Bucket C — org-level (`check_user_permission_or_raise` on `organization:fred`)  ✅ DONE (except 2 service-layer admin methods)
- [x] `kpi/opensearch_controller.py` (23) → `CAN_READ_OPENSEARCH`
- [x] `kpi/prometheus_controller.py` (9) → `CAN_READ_METRICS`
- [x] `kpi/kpi_controller.py` → `CAN_READ_KPI` (per-user) / `CAN_READ_KPI_GLOBAL` (view_global)
- [x] control-plane `kpi/presets/*.py` (10) → `CAN_READ_KPI_GLOBAL` (via workflow)
- [x] `kpi/logs_controller.py` (1) → `CAN_READ_LOGS`
- [x] control-plane `users/api.py` CRUD (zero-authz) → `CAN_ADMINISTER_USERS`
- [x] control-plane `import_export/api.py` (4) + `main.py` policies/lifecycle (3) + `tasks/api.py` (require_admin + admin bypass) + KF `tasks/controller.py` → `CAN_MANAGE_PLATFORM`
- [x] `benchmark/controller.py` (5, zero-authz) → `CAN_RUN_BENCHMARK`
- [ ] KF `metadata/service.py` audit/audit-fix + `tag_service.py` rebac/backfill → `CAN_MANAGE_PLATFORM` (in service files; do with Bucket B @authorize removal)

## AUTHZ-04 — RBAC teardown
- [ ] Remove `RBACProvider`, `authz_providers`, `authorize` decorator, `authorize_or_raise`, `is_authorized`, `require_admin`
- [x] Switch the admin branch of `require_task_access` / ownership to `CAN_MANAGE_PLATFORM`
      — task cancel/stream converged onto `fred_core.tasks.authz` (ReBAC `can_manage_platform`);
      `require_task_access` deleted, legacy `"admin"` role fast-path removed (CTRLP-12, 2026-07-05)
- [ ] Anti-regression: `grep @authorize|authorize_or_raise|require_admin|is_authorized` outside `tests/` returns 0 app hits
- [ ] `make code-quality` + `make test` green across touched packages

---

## Progress

| Item | Status |
| ---- | ------ |
| AUTHZ-02 schema + enums | ✅ done |
| AUTHZ-03 Bucket C (org-level global/admin) | ✅ done (both backends) |
| AUTHZ-03 Bucket A (instance) | ✅ done (content, model umap, scheduler, ingestion[controller-gated], evaluations, audio) |
| AUTHZ-03 Bucket B (@authorize removal + genuine conversions) | ✅ done (metadata, tabular, vector_search, tag, resources, mcp_fs, corpus_manager, cp+kf users) |
| AUTHZ-04 teardown | ✅ done (RBAC machinery removed; display helper added) |
| Zero-authz gaps (KF) | ✅ done: ingestion `fast/*` (fast/delete=DocumentPermission.DELETE, fast/text+ingest=CAN_PROCESS_CONTENT), report `write_report`, `/stat/*` (member-level), vector_search stubs (member-level) |
| Zero-authz gaps (runtime) | ✅ `kpi-turns`→CAN_READ_METRICS, `audit-events`→CAN_MANAGE_PLATFORM (null-safe: allow when caller/engine absent, per RUNTIME-07 dev posture). `list_agents` left public-by-design (returns agent IDs only, like `/templates` + `/mcp-catalog`). |

**Verification (offline suites green, post-teardown):** fred-core 210 · control-plane 175 · knowledge-flow 287.
Zero `@authorize` / `authorize_or_raise` / `require_admin` / `is_authorized` call sites in application code;
`fred_core` no longer exports `RBACProvider`/`authorize`/`authorize_or_raise`/`is_authorized`/`require_admin`.

**AUTHZ-04 teardown (done):** decision (a) — the frontend permission summary now uses a display-only
`fred_core.security.permission_catalog.list_display_permissions` (role→capability hints for UI gating only,
NOT enforcement). Removed: `security/rbac.py`, `security/authorization_decorator.py`, the RBAC functions in
`security/authorization.py` (`authorize_or_raise`/`is_authorized`/`require_admin`/`authz_providers`), and
`AuthorizationProvider` from `security/models.py`. KEPT: `Action`/`Resource`/`AuthorizationError` enums
(ReBAC uses `Resource`), `require_task_access` + session ownership (ownership, not RBAC).

---

## AUTHZ-05 — Fred-owned target authorization model + compatibility bridge  🚧 IN PROGRESS — PR #1957 open, awaiting review

Execution: [PR #1957](https://github.com/ThalesGroup/fred/pull/1957) (closes issue #1912),
branch `1912-authz-05-fred-owned-authorization-model-keycloak-sso-only-fredopenfga-authorization`.
Verified end-to-end (before/after) against a live stack via `fred-deployment-factory`'s
validation suite — see its `validation/report.md`.

RFC: [FRED-AUTHORIZATION-TARGET-MODEL-RFC](../rfc/FRED-AUTHORIZATION-TARGET-MODEL-RFC.md)

Goal: define the next authorization generation for CVSSI and product governance.
Keycloak becomes SSO/OIDC identity only; Fred/OpenFGA owns platform roles, team
roles, team membership, resource permissions, evaluation permissions, and
service-principal authorization. Platform roles do not grant team data visibility.

- [x] Draft the target model RFC for review.
- [x] Confirm bootstrap policy for first `platform_admin` grant (RFC §24.3 — Option A, config-seeded).
- [x] Confirm compatibility window length and bridge modes (RFC §24.1 — 5-7 day audit window, then platform-wide enforce).
- [x] Confirm target relation/capability names (RFC §24.5 — use as-is, no aliasing).
- [x] Swift launch: close the `team.owner = ... or admin from organization` escalation in `schema.fga` before go-live (RFC §24.2 — confirmed live in production today, not hypothetical). Implemented 2026-07-09.
- [x] Swift launch: add `platform_admin`/`platform_observer` relations + config-seeded bootstrap (RFC §24.3). Implemented 2026-07-09, additive only at first — the legacy `admin`/`editor`/`viewer` bridge these relations sat alongside was later removed outright, see the review-item-8a row below.
- [x] ~~Deliberate, narrow exception: `can_administer_owners`/`can_administer_managers` also accept `platform_admin from organization`~~ **Tried 2026-07-09, reverted the same day — PR #1957 review (P1, confirmed):** OpenFGA can't express "only if this team has no owner yet", so the grant applied to *every* team, always. Since `teams/service.py`'s `add_team_member`/`update_team_member` check exactly that capability with no other gate, a `platform_admin` could self-promote to owner/manager of any existing team and inherit full team data access — the exact escalation this item exists to close, through a different door. Reverted to owner-only, no exception. See RFC §24.7.
- [x] Swift launch: one-time translation of existing Keycloak admin/editor/viewer holders and stored team owner/manager tuples into target relations (RFC §18, §24.1) — handled by `fred-deployment-factory/bin/fredlab-authz-migrate-swift.py` (plan/install-model/apply/validate), which this pass's schema rename now matches exactly (`team_admin`/`team_editor`/`team_member`, no CLI-side changes needed).
- [x] Team-role vocabulary rename (`owner`→`team_admin`, `manager`→`team_editor`, +`team_analyst`) across `schema.fga`, `teams/schemas.py`, `teams/service.py` (3 endpoints + admin-safety invariant), `evaluations/api.py` (`CAN_RUN_EVALUATIONS`), frontend `TeamSettingsMembersTable.tsx`, and generated OpenAPI client. Implemented 2026-07-09 (second pass). Note: RFC originally said `team_manager` — corrected to `team_admin` to match the deployment-factory tool's existing `--target-team-admin-relation` default (RFC §26).
- [x] **§25a fixed for the sites where team-scoping is mechanically meaningful** (RFC §27): 9 direct call sites moved from `OrganizationPermission.CAN_READ_CONTENT`/`CAN_PROCESS_CONTENT` to `TagPermission`/`DocumentPermission` on the concrete object (`statistic.list_datasets/set_dataset`, `vector_search.similarity_search/get_visual_evidence_artifact/rerank`, `corpus_manager.build_toc/revectorize/purge`, `scheduler.process_documents`), plus the 15 in-memory statistic calls re-checking the tag authorized at `set_dataset` time. `corpus_manager.capabilities/tasks_get/tasks_result/tasks_list` and `report_controller.write_report` gained a required `team_id`/`tag_id` field (small additive contract change) so they can be team-scoped too — this is what flips the two `xfail` tests in `validation/scenarios/test_content_scope_bypass.py`. Remaining ~17 sites (audio transcription, fast_markdown/fast_ingest, dummy/echo routes) are genuinely resource-less utilities, left org-scoped and documented as such in `rebac_engine.py` — not a gap.
- [x] **Team-bootstrap problem resolved** (RFC §28, later revised by review item 9 — see below): reading `teams/service.py` in full found there was no team-creation flow at all — a "team" is a Keycloak root group discovered lazily, and `add_team_member` requires the group to already exist, so a freshly created group was unreachable by every membership endpoint. Implemented `POST /teams { name, initial_team_admin_ids }` gated by the existing `can_create_team` capability, one-shot by construction (409 if the team exists — cannot be replayed against an existing team, unlike the reverted `§24.7` attempt). At this point (2026-07-09) it still created a Keycloak group alongside the OpenFGA writes; that step was removed the next day, see review item 9.
- [x] **AUTHZ-05 review, 2026-07-09/10 (`NOTES-AUTHZ05-REVIEW.md`, not the RFC itself — a post-implementation pass triggered by human review of PR #1957).** All code items closed except 8b (blocked on the real production data migration having run — deployment task, not a design question):
  - Items 1a/1b/2/3/4 (independent authz-wiring fixes: prompt-mutation endpoints, agent-template/instance GETs, `/process-documents` empty-tags bypass, platform-stats team scoping, Keycloak-role-derived frontend admin surfaces) and item 6 (deleted the unused, dangerous `authz_migration.py` auto-mapping script) and item 7 (confirmed `team_admin` stays a "super `team_member}`" by design) — all closed 2026-07-09.
  - **Item 5 — `can_create_team` cut from `admin or platform_admin` to `platform_admin`-only.** No other caller in the repo checked this capability against the legacy `admin` relation, so the Keycloak bridge was cut here first, ahead of the wider item 8a removal.
  - **Item 8a — the legacy Keycloak `admin`/`editor`/`viewer` organization relations are removed from `schema.fga` entirely** (2026-07-10): Keycloak is now identity-only, no role bridge of any kind survives. The 5 admin-tier capabilities they used to satisfy (`can_administer_users`, `can_manage_platform`, `can_run_benchmark`, `can_edit_agent_class_path`, `can_read_kpi_global`) are `platform_admin`-only now, same pattern as item 5. The 7 "any connected user" capabilities they used to satisfy (`can_read_content`, `can_process_content`, `can_create_agent`, `can_read_kpi`, `can_read_logs`, `can_read_metrics`, `can_read_opensearch`) never protected anything specific — removed outright, not replaced by another relation; the corresponding endpoints rely on authentication alone.
  - **Item 9 — teams decoupled from Keycloak entirely** (RFC Part 6 §29-32, 2026-07-10): a team is now purely a `team_metadata` row (`id`, `name`) plus its OpenFGA relations — `POST /teams` no longer creates a Keycloak group (generates `uuid4().hex` instead), `list_teams`/`get_team_by_id`/`list_team_members`/`add_team_member`/`remove_team_member`/`update_team_member` make zero Keycloak calls. 3 new platform-admin-only, registry-governance-only capabilities added: `can_list_all_teams` (`GET /teams/all`), `can_delete_team` (`DELETE /teams/{team_id}`), `can_rescue_team_admin` (`POST /teams/{team_id}/rescue-admin` — writes a `team_admin` tuple only if the team currently has zero `team_admin`, the guard that keeps it structurally different from the reverted `§24.7` escalation).
  - **Item 8b — closed 2026-07-13, see the dedicated cleanup entry below.** At the time of this review pass it was still blocked pending `fredlab-authz-migrate-swift.py` running against real production data; that data-migration confirmation was never obtained as such — instead Dimitri explicitly waived the precondition (2026-07-13), because `fred-deployment-factory` is being rebuilt from a clean slate with no production membership data to preserve, and the (separate) migration concern is being tracked independently there. Removal proceeded on that explicit waiver, not on the 2026-07-09 verbal confirmation.
  - Verified end-to-end: fred-core, control-plane-backend, knowledge-flow-backend, fred-runtime offline suites green, `make code-quality` clean on all four, frontend `tsc`/`prettier` clean, Alembic migration upgrade/downgrade verified.
- [x] **Live-campaign findings, 2026-07-11 (`NOTES-AUTHZ05-REVIEW.md` items 10-11, found while standing up the `fred-deployment-factory` validation campaign — not the RFC itself):**
  - **Item 10 — `promote_prompt` cross-team write gap.** Only the source team was permission-checked; the target team was never resolved, letting a `team_editor` copy a prompt's text into any `team_id`, including one they held no relation to. Fixed: resolve the target team under the same `CAN_UPDATE_RESOURCES` requirement as the source. Locked by a live regression scenario in `validation/scenarios/test_prompt_authz.py` plus a unit wiring test.
  - **Item 11 — dead second frontend permission system.** `usePermissions()`/`PermissionSummary.items` (Keycloak-role-derived) sat alongside the correct OpenFGA-derived `useUserCapabilities()`. Since AUTHZ-05 removed Keycloak app roles, `items` had gone permanently empty, silently disabling 6 routes and 3 in-page controls for **everyone, including `platform_admin`**. Replaced with one two-tier hook pattern (`useUserCapabilities` org-level / `useTeamCapabilities` team-level), documented in the new `docs/swift/platform/FRONTEND-AUTHZ-PATTERN.md`; `PermissionSummary` shrunk to its two OpenFGA-derived booleans (`CONTROL-PLANE-PRODUCT-CONTRACT.md` §14). Also added a live "authorization self-test" to `/admin/self-test` (runs against the current admin's own session or any other account via Keycloak direct-grant, dev/test realms only) so "does the UI honor the model" is a self-service, in-browser answer going forward, not just a manual checklist.
  - New live scenario files added to `validation/scenarios/`: `test_prompt_authz.py`, `test_team_registry_authz.py`, `test_platform_admin_capabilities.py` — 215 live assertions total.
  - Verified: fred-core 262 passed/1 skipped, control-plane-backend 264 passed, frontend 326 passed + `tsc`/`prettier` clean, `make code-quality` clean.
- [x] **Live-campaign findings, 2026-07-11 continued (`NOTES-AUTHZ05-REVIEW.md` items 12-16, found running the manual persona-by-persona pass against the live `fred-deployment-factory` stack):**
  - **Item 12 — `GET /teams/all` leaked the caller's own personal space into the registry.** Not a cross-tenant leak (verified: `platform_admin` read only their own personal prompts), but a false positive in the new authz self-test. `list_all_teams_for_registry` now filters `personal-*` ids out of `list_all_teams_unfiltered`'s result.
  - **Item 13 — `Protected` (item 11's route guard) redirected to `/unauthorized` before `/frontend/bootstrap` had loaded**, on every hard refresh, with no way back. `useUserCapabilities()` now relays `isLoading`; `Protected` waits for it before deciding.
  - **Item 14 — platform-wide member/admin counts silently showed 0 on "Données plateforme".** `compute_platform_stats` called the permission-checked `list_team_members` with the caller's own identity, which 403s on every real team a `platform_admin` isn't personally a member of (the common case). New `list_team_members_unfiltered` (same contract as item 3's `list_all_teams_unfiltered`) bypasses the per-team check.
  - **Item 15/16 — `platform_observer` had no reachable KPI dashboard, and `/admin/analytics` was wrongly admin-only.** A first attempt widened `/admin/analytics`'s route guard alone, which still 403'd against the backend (`can_read_kpi_global`, platform_admin-only). Root cause: `can_read_kpi_global` was a legacy (`Action.READ_GLOBAL`) capability, separate from the RFC's actual target vocabulary (§6.1 defines only `can_observe_platform` for this purpose) — introduced as an admin-tier capability by item 8a and never reconciled with `can_observe_platform`. Per explicit product decision (Dimitri, 2026-07-11): today `platform_admin` and `platform_observer` see the same platform-wide recap; only `platform_admin` sees the other `/admin/*` pages (team registry, task activity, platform data, self-test). Resolution: `can_read_kpi_global` retired from `schema.fga` entirely; the 10 Analytics preset endpoints (`control-plane-backend/kpi/presets/*.py`) and the standalone KPI dashboard (`/monitoring/kpis`) both now check `can_observe_platform`. `/admin/analytics` requires `observer`; a new capability-aware `AdminIndexRoute` sends a `platform_admin` to `/admin/teams` and a `platform_observer`-only user to `/admin/analytics`. When the Analytics dashboard grows admin-only technical panels, gate those specific widgets on a new, narrower capability instead of resurrecting the old split.
  - Verified: fred-core, control-plane-backend, knowledge-flow-backend offline suites green, `make code-quality` clean on all three, frontend `tsc`/`prettier`/`vitest` clean. `schema.fga.json` regenerated.
  - **Item 17 — authorization self-test enriched with a real write probe.** The browser self-test (`/admin/self-test`) only ever checked denials (isolation) — no step proved that a *granted* write permission actually works. New `team-write-access` step: reads the target account's own `permissions` on their first team (`GET /teams/{id}`), attempts a real, run-scoped, immediately-cleaned-up prompt create, and asserts the result matches `can_update_resources`. Frontend-only, `authzProbeScenario.ts`/`useAuthzProbeRun.ts`, 10 new unit tests.
- [x] **Cleanup — removed the obsolete periodic Keycloak groups→ReBAC reconciliation (2026-07-13).** Knowledge Flow ran a 15-minute background task (`security/keycloak_rebac_sync.py`, `main.py` lifespan) reconciling Keycloak group membership into ReBAC `team_member` tuples. With the OpenFGA engine, `RebacEngine.need_keycloak_sync` was already hardcoded `False`, so the task always no-opped — a dead path left over from before AUTHZ-05 made Keycloak identity-only. Deleted the module, the lifespan task, and the now-unused `need_keycloak_sync` property; kept `RebacEngine.list_relations` (still abstract, implemented by 2 engines, exercised elsewhere) but fixed its OpenFGA-stub comment which referenced the deleted sync. Mechanical fix, exempt from a new RFC entry (CLAUDE.md) — same PR #1957 / branch, no new ID.
- [x] **Item 8b closed — removed the Keycloak JWT `groups`-claim-derived `team_member` fallback (2026-07-13).** `groups_list_to_relations`/`_user_contextual_relations` (`libs/fred-core/fred_core/security/rebac/rebac_engine.py`) built a contextual `team_member` relation from the caller's `groups` claim and injected it into every `lookup_user_resources`/`has_user_permission`/`check_user_permission_or_raise` call; `control_plane_backend/teams/service.py::_get_team_permissions_for_user` called it directly. Both are removed outright — no fallback, no toggle. `RebacEngine.__init__`/`self.keycloak_client` (used only to build this fallback) removed too, along with the `m2m_security` parameter threaded through `OpenFgaRebacEngine.__init__`/`rebac_factory.py`/`NoopRebacEngine`; the global M2M config (used for identity/directory Keycloak calls elsewhere) is untouched. **Known scope note:** the removed method also carried an unconditional, non-`groups`-derived "user is a member of their own personal team" contextual relation (`team:personal-<uid>`, keyed off `user.uid`, never persisted as an OpenFGA tuple anywhere). It was removed too, on Dimitri's explicit instruction to follow the literal scope rather than carve out an exception — traced call sites (`tag_service.py::create_tag_for_user`, `teams/system.py::build_personal_team`) suggest personal-space resources are owned directly by `user`, not `team:personal-<uid>`, and the personal "team" itself resolves via a hardcoded synthetic permission set that never calls ReBAC, so this is believed low-risk but was not exhaustively proven safe across every resource type (agents, corpus_manager, evaluations) — flagged here as a live-validation watch item, not closed as risk-free. New tests: `libs/fred-core/fred_core/tests/security/test_rebac_engine_team_helpers.py` (3 unit tests proving `contextual_relations` is always `None` from the 3 wrapper methods), `libs/fred-core/fred_core/tests/integration/test_rebac.py` (2 OpenFGA integration tests, negative/positive, written but not executed live this session — see below), `apps/control-plane-backend/tests/test_team_permissions_no_groups_fallback.py` (2 unit tests on `_get_team_permissions_for_user`). Verified offline: fred-core 255 passed, control-plane-backend 277 passed, `make code-quality` clean on both. The 2 new OpenFGA integration tests were not run against a live instance this session (assistant's static/deterministic reasoning from `schema.fga`'s `Check` semantics substituted for a live run, per Dimitri's instruction) — recommend running them (`pytest -m integration`) before merge.
- [x] **Final mechanical sweep — every remaining Keycloak-groups producer/consumer removed (2026-07-13), same PR/branch, no new ID (mechanical completion of item 8b's scope, CLAUDE.md exemption).** `KeycloakUser.groups` (`libs/fred-core/fred_core/security/structure.py`) deleted; `oidc.py::decode_jwt` no longer reads `payload.get("groups", [])` in any of its 3 `KeycloakUser(...)` construction sites — a JWT `groups` claim now decodes successfully and is silently ignored end to end (new test: `test_oidc_strict.py::test_groups_claim_is_accepted_but_ignored`). Every `KeycloakUser(..., groups=...)` fixture across `apps/control-plane-backend`, `apps/knowledge-flow-backend`, `libs/fred-core`, `libs/fred-runtime` tests updated to drop the kwarg. **`KPIActor.groups` removed** (`kpi_writer_structures.py`) — its only producers were `KeycloakUser.groups` copies in `kpi_writer.py::to_kpi_actor`, `ingestion_controller.py`, and `vector_search_service.py::_kpi_actor`, all fixed; the `groups` KPI dimension and its OpenSearch mapping (`opensearch_kpi_store.py`, both the fresh-index mapping and the additive `_ensure_dim_mapping` migration) removed with it — no independent producer existed. **`RuntimeContext.user_groups` removed** (`libs/fred-sdk/fred_sdk/contracts/context.py`) after tracing every producer/consumer: `agent_app.py` fed it from `ctx.get("user_groups")`, a dict key no backend ever set and no frontend `src/` code (only the generated OpenAPI types) ever populated — a confirmed dead Keycloak vestige, not a generic/independent context field, so removed rather than kept-with-comment. Its only 2 consumers (`react_runtime.py`, `graph_runtime.py`) fed it straight into the now-gone `KPIActor.groups` via a `MetricsProvider.timer(groups=...)` parameter threaded through `fred_core/portable/observability.py` (`MetricsProvider`/`LoggingMetricsProvider`/`InMemoryMetricsProvider`, the latter already silently dropping it) and `fred-runtime`'s `_MetricsTimerAdapter` — the whole `groups` parameter removed from that interface too. This is a frozen-contract field change (`RuntimeExecuteRequest.runtime_context`, exposed over the wire): regenerated `libs/fred-runtime/openapi.json` (`make generate-openapi`, gitignored artifact) and `apps/frontend/src/slices/runtime/runtimeOpenApi.ts` (`make update-runtime-api`, 1-line diff, frontend `tsc --noEmit` clean); documented in `RUNTIME-EXECUTION-CONTRACT.md` §8.13. `apps/frontend/src/slices/agentic/agenticOpenApi.ts` still shows a stale `user_groups` field — left untouched, no Makefile regen target reaches it (looks like a dead/legacy generated file, out of scope for this mechanical pass). Docs updated: `KEYCLOAK.md` (dropped `query-groups`/`view-groups`/group-membership `manage-users`/groups/`groups-scope`/`oidc-group-membership-mapper` instructions), `REBAC.md` (corrected the "`groups` claim may still be decoded" line, now false), `FEATURES.html` ("Platform roles are global (Keycloak groups)" → OpenFGA), `COPYLEFT-DEPENDENCIES.md` (`KeycloakAdmin` method/file counts corrected: 9→4 methods, 6→4 files, `teams/service.py`/`teams/dependencies.py` no longer touch it at all), `apps/control-plane-backend/README.md` + 3 stale `teams/service.py` docstrings ("Removes user membership from Keycloak group" was already false — the code only writes/deletes ReBAC relations). Fixed the misleading `openfga_engine.py::list_relations` comment for real this time (id-legend claimed it was already fixed; it wasn't — still said "OpenFGA resolves group membership through contextual tuples"). Verified offline: fred-core 256 passed, fred-sdk 186 passed, fred-runtime 417 passed, knowledge-flow-backend 356 passed, control-plane-backend 277 passed; `make code-quality` clean on all five; frontend `tsc --noEmit` clean. No live tests run this session.
- [x] **AUTHZ-06 — Cumulative team roles (RFC Part 7, `docs/swift/rfc/FRED-AUTHORIZATION-TARGET-MODEL-RFC.md` §33-39), code-complete 2026-07-12.** A user may hold `team_admin`+`team_editor`+`team_analyst` on the same team simultaneously — `update_team_member` used to enforce exactly one role per user per team, making the common small-team shape (one person governs, edits, and evaluates; a few plain members) structurally unreachable. `schema.fga`: **no change** — OpenFGA already permits multiple relation tuples per user per object; the exclusivity was a service-layer convention only. `update_team_member`/`PATCH /teams/{team_id}/members/{user_id}` retired, replaced by `grant_team_member_role`/`POST .../roles` and `revoke_team_member_role`/`DELETE .../roles/{relation}` — one role granted or revoked per call, same per-role permission checks as today, revoke refuses to empty a member's last role. Contract change: `TeamMember.relation` (singular) → `relations` (list) — `CONTROL-PLANE-PRODUCT-CONTRACT.md` §15. `TeamSettingsMembersTable.tsx` reworked to independent per-role toggle chips. Verified: control-plane-backend 275 passed (9 new), `make code-quality` clean; frontend `tsc`/`prettier`/`vitest` (345 passed) clean. Design updated in `docs/swift/platform/REBAC.md`. **Not yet done: the live validation campaign** (`make validation-report`, deployment-factory test profiles, manual UI pass, campaign registry) — tracked in `NOTES-AUTHZ05-REVIEW.md`. Continuing under existing GitHub issue #1912 / PR #1957, same branch.
- [x] ~~Swift launch (deployment task, not code): populate `platform_admin_subjects`/`platform_observer_subjects` in the swift deployment config (`fred-deployment-factory`) with the known existing admin/viewer population~~ **Superseded 2026-07-13 (RFC Part 8, `AUTHZ-07`):** embedding a Keycloak `sub` in deployment config was reconsidered as fragile and unreviewable (an opaque per-realm UUID in versioned/secret config, invalid the moment the realm is re-imported). Replaced by Option D — see next item.
- [x] **AUTHZ-07 Phase 1 — root platform-admin bootstrap endpoint, first pass code-complete 2026-07-13 (RFC Part 8, §40-41).** `apps/control-plane-backend/control_plane_backend/bootstrap/`: `POST /bootstrap/platform-admin { identifier, token }`, deliberately public, resolved `identifier` via the Keycloak Admin client, guarded by a live `lookup_subjects` check. Manually validated end-to-end on `fred-deployment-factory`'s `docker-up` (new default empty world). Superseded by the review pass below before any K8s templating — see next item.
- [x] **AUTHZ-07 review pass, revised 2026-07-14 (RFC Part 8, §42) — two gaps found before merge, both closed.** Found while reasoning through the real GKE/AKS rollout: (1) an attacker holding only the deploy secret — no Fred identity — could name any existing Keycloak user by `identifier` and grant them `platform_admin` without their knowledge; (2) the live `lookup_subjects` guard is the same bug shape as the reverted `§24.7` escalation — a condition true only "for now" treated as a standing safety property, so removing every `platform_admin` later would silently reopen bootstrap for anyone still holding the secret. Corrected:
  - **JWT required** (`get_current_user`) in addition to the deploy secret — two independent proofs, neither sufficient alone. Does not reopen the bootstrap chicken-and-egg: Keycloak authentication depends on nothing Fred/OpenFGA owns.
  - **`identifier` removed from the request.** The grant always targets the calling JWT's own `sub` — structurally cannot promote a third party. Also drops the Keycloak Admin client dependency entirely from this endpoint (simpler, not just safer).
  - **Durable completion marker**, not a live count: new `PlatformBootstrapStore` (`libs/fred-core/fred_core/platform/`, table `platformbootstrap`, Alembic migration `6e4149d46705`) — a persisted row, written *before* the OpenFGA tuple under the same `advisory_lock` primitive `rescue_team_admin` uses. A crash between the two writes leaves bootstrap durably marked complete with no admin granted — fail-closed, recoverable only through a separate break-glass procedure (explicit non-goal, `§41`), never a silent reopening.
  - **Secret never generated or logged by Fred**, in any environment. `AppConfig.bootstrap_token_env_var` (checked first — a Kubernetes Secret via the deployment's existing secrets pipeline, RFC-0001 §6's "secrets source" knob, no new mechanism) or `bootstrap_token_file` (local dev only, created explicitly via `make bootstrap-token` — the app no longer self-generates or prints it at startup).
  - Registered in `docs/swift/platform/authz-endpoint-matrix.yaml` as `external_or_public` (updated description: authenticated but not ReBAC-gated). Documented in `CONTROL-PLANE-PRODUCT-CONTRACT.md` §3.1.2 and `REBAC.md`.
  - Verified offline: fred-core 256 passed, control-plane-backend 290 passed (9 in `test_bootstrap_platform_admin.py`, including the load-bearing regression test proving the durable marker — not admin count — blocks reuse after simulated total `platform_admin` loss), `make code-quality` clean on both (ruff, bandit, basedpyright). Migration upgrade/downgrade verified in isolation.
  - **Pre-existing, unrelated finding (not fixed here, flagged for a separate item):** `alembic/env.py` imports `fred_core.documents.document_models` for autogenerate visibility, but the `metadata`/`tag` tables it registers have no migration in control-plane-backend's own chain — `make db-check-sqlite`/`db-check-postgres` both fail on this today, independent of AUTHZ-07 (confirmed via `git blame`: introduced 2026-07-07, `565d884f`).
  - **Not yet done:** manual end-to-end re-validation on `docker-up` with the revised JWT-required flow, then Phase 2 (Kubernetes Secret templating for GKE/GCP), then Phase 3 (AKS/Prism). Part (2) of the original scope — one declarative platform-provisioning operation for teams/roles/users, likely a hardened/generalized `PLATFORM-IMPORT-RFC.md` — remains open, to confirm with that RFC's owner before implementation.
- [x] **AUTHZ-07 hardening pass, 2026-07-14 (same day as the §42 revision above) — 9 findings verified and fixed, one at a time with developer sign-off, before the first local-docker test.** Findings 1-5 came from an independent review (Codex); each was re-derived against the actual code before being accepted, not taken on faith.
  1. **Empty/trivial configured secret accepted** — `secrets.compare_digest("", "")` is `True` in Python, so an empty configured secret (e.g. a broken `make bootstrap-token` run) would compare equal to an empty request token. Fixed at both layers: `BootstrapPlatformAdminRequest.token` now `min_length=16`; `_read_configured_token` treats any configured value under that floor (env or file) as unconfigured, never returned for comparison.
  2. **`make bootstrap-token` fail-open** — `openssl rand -hex 32 > FILE; echo "Created"` used `;` not `&&`: a failed `openssl` still printed success and left an empty file at the final path. Rewritten atomic (write to `.tmp`, `mv` into place), `umask 077` (600 permissions from creation, no chmod race), fails loudly (`exit 1`, stderr message, cleans up the `.tmp`) on any step's failure.
  3. **Write order could brick bootstrap forever on a transient OpenFGA failure** — the durable marker was written *before* the OpenFGA tuple, and `mark_completed()` commits in its own Postgres transaction; a network blip on the very first bootstrap call left the marker permanently set with no admin ever granted, no recovery path. Reordered: OpenFGA tuple written first (already idempotent via `on_duplicate_writes=IGNORE`, the same mechanism `_bootstrap_platform_roles` already relies on), marker second — a crash/failure between the two writes is now a safe, idempotent retry instead of a permanent lockout. RFC §42.3 updated to match (second same-day revision note).
  4. **Env-var-to-file fallback contradicted the documented contract** — `bootstrap_token_file`'s own docstring says "ignored if `bootstrap_token_env_var` is set", but the code silently fell back to the file whenever the named env var was absent/too short. Fixed to fail closed (`None`, never fall through to the file) the instant an env var name is configured.
  5. **ReBAC disabled silently burned the one-time marker** — `NoopRebacEngine.add_relation` is a no-op; with ReBAC disabled, bootstrap would durably mark itself complete while granting nobody `platform_admin`, permanently. New fail-closed guard (`BootstrapRebacDisabledError`, 503), checked before the store is touched.
  6. **Found while writing gap 5's test, not in the original review**: `get_current_user` returns a hardcoded mock identity with zero validation whenever Keycloak/OIDC is disabled (`security.user.enabled=False`) — silently degrading the RFC's stated "two independent proofs" (§42.1) to one (the deploy secret alone). Symmetric fail-closed guard added (`BootstrapAuthDisabledError`, 503), checked *first* (authentication is the more fundamental of the two proofs).
  7. **Minimality**: `PlatformBootstrapStore`/`PlatformBootstrapRow` had zero consumers outside `control-plane-backend` — unlike `TeamMetadataStore`, which has a real second consumer in `knowledge-flow-backend` and correctly stays in `fred-core` for that reason. Moved out of `libs/fred-core/fred_core/platform/` (deleted entirely) into `control_plane_backend/bootstrap/store.py` + `control_plane_backend/models/bootstrap_models.py`; switched from the shared `CoreBase` to control-plane-backend's own local `Base` (matching `PurgeQueueRow`/`SessionAttachmentRow`'s existing pattern). Pure relocation, zero schema change — verified zero Alembic drift (`make db-check-heads` clean; `make db-check-sqlite`'s `alembic check` diff shows only the pre-existing, unrelated `metadata`/`tag`-table finding noted two bullets above, nothing about `platformbootstrap`).
  8. **Test coverage gaps closed**: a real `PlatformBootstrapStore` test against a live SQLite engine (`test_metadata_stores.py`, reusing its existing `_make_sqlite_engine` helper — every bootstrap test before this used hand-rolled fakes only); route-level tests through the real ASGI app (`test_main.py`) proving 401 without a bearer token, 503 when auth is disabled, and a full 200 happy path; a genuine concurrency test (`test_bootstrap_platform_admin.py`) proving the advisory lock actually serializes two racing legitimate callers — required making `_FakeBootstrapStore`'s lock a real `asyncio.Lock` plus explicit yield points (a naive fake never actually interleaves two `asyncio.gather`'d coroutines); independently re-verified by reverting the lock and confirming the test then fails (`2 == 1`, a genuine double grant) before restoring it.
  9. **Generated client regenerated** (`make update-control-plane-api`) — untouched since Phase 1, stale; also added explicit `responses={403, 409, 503}` to the route decorator so the fail-closed guards are documented in the OpenAPI spec and generated client, not only returned at runtime.
  - Verified offline: control-plane-backend 304 passed (full suite, not just touched files), fred-core 256 passed offline (17 pre-existing OpenFGA-live integration test failures, unrelated, no local OpenFGA server available in this environment), frontend `tsc --noEmit` clean. `make code-quality` not run this session (developer's own gate) — outstanding before merge.
  - **Still not done** (unchanged from the row above): manual end-to-end re-validation on `docker-up`, Kubernetes Secret templating for GKE/GCP then AKS, and part (2) of the original AUTHZ-07 scope (declarative platform-provisioning for teams/roles/users).
- [x] **AUTHZ-07 Part (2) closed, 2026-07-14 — declarative team/platform role provisioning via `import_export`.** Implements `FRED-AUTHORIZATION-TARGET-MODEL-RFC.md` Part 8 §40.2's "harden and generalize `PLATFORM-IMPORT-RFC.md`'s input contract" recommendation; full design in `PLATFORM-IMPORT-RFC.md` §10. A new top-level `users.json` bundle entry names already-existing Keycloak identities by username and describes the team/platform roles they should hold; resolution is read-only (`users/service.py::find_user_sub_by_username`, never creates a Keycloak identity — an unresolved username is skipped and reported). Platform-role grants to a third party are the one genuinely new capability, kept to a single private helper (`importer.py::_grant_platform_role`) reachable only through the already `CAN_MANAGE_PLATFORM`-gated import route — no new endpoint. Team-scoped grants stay bounded by the existing, deliberately non-escalating permission model (`schema.fga`: `team_admin`-only, never derived from a platform role, per the reverted `§24.7` precedent): a brand-new team's initial `team_admin`(s) can be seeded at creation (`teams.service.create_team`'s own bootstrap capability), but any other team-scoped grant requires the importing `platform_admin` to already hold `team_admin` there — otherwise it is skipped and reported (`report.team_roles_skipped`), never forced through. Verified offline only: `tests/test_import_export_users.py` (8 tests: resolved-user success path, graceful skip of a grant the caller can't make, unresolved-username skip, re-run idempotency, and `find_user_sub_by_username` never calling a Keycloak write method), full control-plane-backend suite 314 passed. Frontend `controlPlaneOpenApi.ts` regenerated (no fields changed by this work; the diff picked up was pre-existing, unrelated bootstrap-endpoint drift) and `tsc --noEmit` clean. `make code-quality` not run this session (developer's own gate).
- [x] **`fred`/`fred-deployment-factory` boundary split, Part A closed, 2026-07-14 — typed bundle + 2-phase import (identity then role).** `fred` (`control_plane_backend/import_export/`) becomes the sole, complete owner of platform provisioning — identities *and* authorization state — closing the design smell found while testing AUTHZ-07's bootstrap live (demo identity/authz data mixed into `fred-deployment-factory` config; `openfga-post-install.sh` unconditionally seeding `platform_admin` tuples in both authz modes). New `import_export/schemas.py::BundleUserEntry` (Pydantic) retypes `KBundle.demo_users()` from `list[dict[str, Any]]` to `list[BundleUserEntry]`, validated per entry (`bundle.py`); carries the pre-existing role fields (`teams`/`team_roles`/`platform_roles`) plus new optional identity fields (`email`/`first_name`/`last_name`/`password`). New `importer.py::_provision_bundle_identities` (phase 1, runs before the unchanged role phase in `_run_users_phase`) creates a Keycloak user via the existing `users/service.py::create_user` only when both no identity resolves yet and the entry carries a `password` — never force-created, never overwrites an existing identity; `KeycloakM2MUserOperationDisabledError` propagates uncaught if M2M isn't configured. New `MigrationReport.identities_created` field. New checked-in fixture `apps/control-plane-backend/tests/fixtures/import_export/demo_provisioning/{manifest.json,users.json}` — the 15 demo users (retyped from `fred-deployment-factory/config/configuration.yaml`'s `users:` list, dropping `enabled`/`app_roles`/`_purpose`, keeping the `Azerty123_` convention), now the *only* place this data exists; `make build-demo-bundle` (new Makefile target) zips it to `target/demo-provisioning-bundle.zip` for upload via Admin → Migration. `PLATFORM-IMPORT-RFC.md` §10 extended (not rewritten) with the identity phase, `BundleUserEntry`'s full shape, the M2M precondition, and the fixture's new content/location (new §10.1). Verified offline: `tests/test_import_export_users.py` — the success-path test now reads the checked-in fixture end-to-end (all 15 identities created, 3 teams provisioned, 4 free team_admin grants, 10 correctly-skipped team-scoped grants, 2 platform-role grants) instead of a hand-rolled single-entry dict; every other test in that file keeps its hand-rolled dict on purpose (edge cases that must not match the real fixture); one new dedicated unit test on `_provision_bundle_identities` asserting the exact `a_create_user` payload and that an already-resolved or password-less entry is never created — 9 tests total (was 8), full control-plane-backend suite 315 passed (was 314). Fixture round-trips through `BundleUserEntry.model_validate` (confirmed 15 entries). `make build-demo-bundle` confirmed to produce a zip containing exactly `manifest.json`+`users.json`. This is Part A of a 3-part plan (Part B: strip `fred-deployment-factory` to pure infrastructure; Part C: relocate `validation/` into `fred/validation/`) — Parts B/C tracked separately, out of scope for this bullet.

### AUTHZ-07 candidate hardening workplan — recorded 2026-07-14

This is the durable execution plan for the candidate review. It extends AUTHZ-07
and the existing RFCs; it does not introduce a new feature or architecture.

Candidate baselines:

- `fred`: `98ae82b6` (`#1986 add root admin bootstrap and declarative platform provisioning`)
- `fred-deployment-factory`: `e6c82fa` (`#1986 remove business configuration and leave only infrastructure setup`)
- Development bootstrap proven live from scratch: register `alice` in Keycloak,
  authenticate, submit the one-time token, become the first `platform_admin`,
  continue into Fred.

Execution protocol:

1. Work strictly one step at a time; do not mix steps in one implementation.
2. Observation comes before correction. Retain evidence before changing behavior.
3. Before each implementation step, Codex writes a precise Claude prompt from
   the evidence collected in the previous step; Dimitri confirms it before
   Claude starts.
4. Each Claude invocation must re-derive the finding from the current code,
   obey `CLAUDE.md`, stay inside the named step, run the required checks, and
   produce one logical commit. Do not push unless explicitly requested.
5. Record the final prompt and resulting commit under the matching step here,
   so that the handoff remains reproducible outside the chat history.

- [x] **Step 1 — live import observation, no product-code change. Done 2026-07-14.**
      Built `apps/control-plane-backend/target/demo-provisioning-bundle.zip`, uploaded it
      through Admin → Migration, retained the visible task state/report and backend
      warnings, then ran root `make validation-report`. Captured: import task id,
      terminal status, created identities/teams, granted/skipped roles, UI
      warnings, failed validation scenario names, and relevant logs. No fix
      applied during this step.
  - Exit gate: the complete command/UI evidence is returned to Codex. **Met.**
  - Claude prompt: none; this was a human-driven observation step.
  - Result: development bootstrap proven live from a fresh platform (Keycloak
    self-registration → authenticated one-time bootstrap → first `platform_admin`
    → Fred). The real demo bundle import then produced: `task_id
    b9f88fac-e03b-4309-bcf7-ff48fea6601b`, `import_id
    c77689e0-3c32-48a9-8212-f65b478ade9f`, 3 teams created, 4 initial `team_admin`
    grants, **10 team roles ignored**, task terminal state `succeeded` (the bug:
    a silently incomplete success). The 10 ignored roles: bob (`team_editor` on
    `northbridge`+`fredlab`), phil (`team_member` on `northbridge`+`swiftpost`),
    zoe (`team_member` on `fredlab`), liam (`team_member` on `swiftpost`), elena
    (`team_analyst` on `fredlab`), derek (`team_editor` on `northbridge`), priya
    (`team_editor`+`team_analyst` on `fredlab`). Root cause confirmed from code:
    `importer.py::_apply_bundle_user_roles` called
    `teams.service.grant_team_member_role` with the importing `platform_admin` as
    actor; that ordinary API requires the caller to already hold `team_admin` on
    the target team, which the importer deliberately never does (RFC Part 8
    §24.2/§24.7, "zero implicit access") — so every non-admin grant was refused
    and downgraded to a warning. `validation/report.md` at this point: **Result:
    NOT READY — 0 passed, 0 failed, 227 error**, every failure a setup error on
    the same missing relation (e.g. `"'bob' is missing relation(s)
    ['team_editor'] on team 'fredlab'; currently holds []"`) — one design gap
    blocking the platform's common test setup, not 227 independent defects.

- [x] **Step 2 — make declarative import converge completely.** Using Step 1's
      evidence, reconcile every valid identity, team membership, team role and
      platform role requested by the bundle; define the `teams` fallback
      semantics explicitly; reject or fail incomplete/invalid reconciliation
      instead of reporting success after silent skips. Preserve the invariant
      that ordinary team APIs remain team-admin bounded: any exceptional
      provisioning authority must be private to the existing platform-admin
      import operation, narrow, tested, and documented in the existing RFC.
  - Exit gate: the real demo bundle imports with zero unintended skips; targeted
    tests and the affected live validation scenarios pass; rerun is idempotent.
    **Met — live-validated 2026-07-14.** The operator re-imported the same demo
    bundle onto the already-partially-provisioned live stack, then re-ran root
    `make validation-report`: **225 passed, 0 failed, 0 errors, 2 skipped
    (expected)** — the 227-error cascade from Step 1's evidence is gone, and
    the fix holds end to end, not just offline.
  - Scope confirmed 2026-07-14 (developer prompt, reusing this same issue/PR —
    no new task ID): fix `importer.py::_apply_bundle_user_roles` so every
    `team_roles`/`teams` grant the bundle declares is actually written, without
    relaxing the ordinary team-membership permission model or touching
    `schema.fga`. Constraints: no team relation for the importing user itself;
    the exceptional write authority stays private to `POST /import-export/import`
    (already `CAN_MANAGE_PLATFORM`-gated); reuse `RebacEngine`/`Relation`/
    `RebacReference`/`RelationType`, no second public membership service; fail
    closed (raise, abort the users phase) on an unknown role name, an unresolved
    identity after the identity phase, or an unprovisionable team — never
    downgrade to a warning-then-`succeeded` again.
  - Claude prompt/result/commit: implemented 2026-07-14. New private primitive
    `importer.py::_grant_team_role_via_import` (mirrors the pre-existing
    `_grant_platform_role`) writes every team-scoped grant directly via
    `RebacEngine.add_relation`, bypassing the `team_admin`-gated
    `grant_team_member_role` for this import-only path (that ordinary API is
    unchanged and still refuses the same importer — regression-tested). New
    `_effective_team_relations` formalizes the `teams`/`team_roles` fallback:
    an explicit role list wins outright; `teams` with no explicit role for that
    team falls back to a single direct `team_member` tuple; multiple explicit
    roles on one team are cumulative. New `BundleProvisioningError` makes an
    unknown team/platform role name, an unresolved username, or an
    unprovisionable team abort the users phase (`task_service.fail_task`)
    instead of a warning. `PLATFORM-IMPORT-RFC.md` §10 updated in the same
    change. Tests: `tests/test_import_export_users.py` rewritten — the fixture
    end-to-end test now asserts `identities_created=15`, `teams_provisioned=3`,
    `team_roles_granted=14`, `team_roles_skipped=0`, `platform_roles_granted=2`,
    zero warnings; new tests cover non-admin grant on a fresh team, reconciling
    a role on a **pre-existing** team the importer holds no `team_admin` on,
    the ordinary API still refusing the same importer, cumulative roles, the
    `team_member` fallback and its suppression by an explicit role, idempotent
    re-run, and each fail-closed case — 17 tests total, `control-plane-backend`
    full suite green, `make code-quality` clean. Live-verified the same day —
    see this step's exit gate above (`225 passed, 0 failed, 0 errors, 2 skipped`).
    Commit: see `git log` for `fix(AUTHZ-07): make platform import reconcile
    team roles` on branch
    `1986-authz-07-root-platform-admin-bootstrap-and-declarative-platform-provisioning`.

- [x] **Step 3 — make import outcome observable and truthful.** Retain the
      structured migration report, expose it through the existing task/event
      contract, and make the UI show actionable failures/warnings. A partial
      reconciliation must not be indistinguishable from full success.
  - Exit gate: backend contract/event tests plus UI tests prove success, failure
    and warning rendering without a parallel task-status model. **Met.**
  - Claude prompt/result/commit: implemented 2026-07-14, same issue/PR/branch
    (no new task ID). Root cause re-confirmed from the current code: the import
    task was started with no `target` (`task_service.start(StartMigrationRequest(),
    created_by=user.uid)` — no `target=` kwarg despite `TaskTarget` already
    existing on the contract), so `GET /tasks` fell back to the raw `task_id`
    UUID; `import_export/api.py`'s `_run()` discarded `run_import()`'s returned
    `MigrationReport` and emitted an empty terminal `MigrationTaskEvent`; the
    already-present `label` `Form()` field on `POST /import-export/import` was
    accepted but never read; `TaskSummary` had no `detail` field, so even a
    populated `TaskRunRow.detail` (already retained by `TaskStore.record_event`'s
    pre-existing "keep the last non-null detail" rule) never reached `GET /tasks`.
    Design: one canonical pipeline, no parallel one —
    `MigrationReport` → `to_migration_result()` → `MigrationTaskEvent.detail.result`
    → `TaskStore` (existing retention) → `TaskSummary.detail` → the existing shared
    `TaskActivity` component; no new table, endpoint, Redux store, or import-only
    page. Full rationale in `PLATFORM-IMPORT-RFC.md` §11.
    Backend: `fred_core.tasks.models` — new `MigrationResult` (typed projection of
    `MigrationReport`, every field named in the exit gate); `MigrationDetail.result:
    MigrationResult | None = None` (terminal-only); `TaskSummary.detail` (union of
    the existing per-kind Detail models, typed per `kind` like `TaskEvent`, `None`
    for legacy/undetailed tasks). `fred_core.tasks.store` —
    `TaskStore.list_tasks` now projects the persisted detail into the right typed
    model per `kind` (`_parse_task_detail`). `import_export/importer.py` —
    `to_migration_result()` (field-for-field `MigrationReport` → `MigrationResult`,
    no re-derivation). `import_export/api.py` — `_import_target()` builds the
    canonical `TaskTarget` (`type="platform_import"`, `id=import_id`,
    `label=` trimmed operator label → uploaded filename → `"Platform import"`
    fallback), passed to `task_service.start(..., target=...)`; the terminal
    `succeeded` event now carries `progress=1.0`, the canonical `target`, and
    `MigrationDetail(step_id="done", result=to_migration_result(report))`.
    Frontend: `launchPlatformImport.ts::buildImportTarget` reproduces the exact
    same precedence for the optimistic registration (was previously
    `type: "platform"` + `label: file.name` unconditionally, ignoring the operator
    label — fixed to match the backend, not a second source of truth);
    `taskTypes.ts` gained the hand-maintained `MigrationResult` mirror + `detail.result`
    on `MigrationTaskEvent`; `TaskActivity.tsx`/`.module.css` — a `succeeded`
    migration with `result.warnings.length > 0` shows an explicit "with warnings"
    flag next to the state badge (state itself stays `succeeded`, no new
    `TaskState`); a `failed` task now renders `task.error` (was previously never
    shown in this shared component — a real, generic gap, fixed for every kind,
    not just migration); a per-row `Disclosure` (existing design-system atom, not
    a new control) shows the principal non-zero counters and the full warnings
    list, defaulting open when warnings are present so they are not hidden behind
    an extra click. Non-migration kinds unaffected (`detail`/`result` narrowed on
    `task.kind === "migration"` before use).
    Behaviour: success without warnings → plain "Completed" row, no flag, no
    disclosure noise (only shown if there is something to show); success with
    warnings → same "Completed" wording plus an explicit "With warnings" flag and
    an open-by-default disclosure listing counters + every warning string; failed
    → "Failed" row with the `error` message rendered, never the success wording,
    target still resolved to its canonical label (set at creation, survives the
    exception path unchanged).
    Tests: backend — `libs/fred-core/fred_core/tests/tasks/test_models.py` (4 new:
    `MigrationDetail.result` defaults `None` and stays backward compatible,
    terminal round-trip with warnings, `TaskSummary` accepts a typed
    `MigrationDetail`/defaults `detail=None`); `apps/control-plane-backend/tests/test_task_store.py`
    (4 new: typed migration detail incl. nested result projects through
    `list_tasks`, legacy task with no detail reads back `None`, a non-migration
    kind — ingestion — still projects correctly, `ErasureDetail` still parses via
    the generic kind→model mapping); new
    `apps/control-plane-backend/tests/test_import_export_task_observability.py`
    (13 tests: `_import_target` precedence incl. the no-label/no-filename
    fallback, `to_migration_result` maps every field and defensively copies
    lists, and — through the real ASGI route (`create_app()` + `httpx`
    `ASGITransport`, `run_import`/`open_bundle` monkeypatched at the call site so
    only the API layer's own responsibility is exercised) — target set with an
    explicit label, target falls back to the filename, a clean success produces
    the full structured result via `GET /tasks`, a result with warnings survives
    the same round trip and stays `succeeded`, and an exception produces `failed`
    with the error message and the canonical target, never `succeeded`). Frontend
    — `TaskActivity.test.tsx` (8 new: clean success shows no flag, warnings
    trigger the explicit flag, counters/warnings are present in the (open-by-default)
    disclosure, a still-running migration shows no result markup yet, a failed
    task shows its error and never the success text, the backend label is used
    over the raw task id, a non-migration task is unaffected, the disclosure
    toggle is a native `<button aria-expanded>` with a visible accessible name).
    Verified offline: fred-core 260 passed, control-plane-backend 336 passed,
    `make code-quality` clean on both (ruff, bandit, basedpyright); frontend
    `tsc --noEmit` clean, `prettier --check` clean, `vitest run` 353 passed (30
    files). `make update-control-plane-api` regenerated
    `apps/frontend/src/slices/controlPlane/controlPlaneOpenApi.ts` from the new
    `openapi.json` (new `MigrationResult`/`ErasureDetail`/etc. schemas plus
    `TaskSummary.detail`) — no hand-written type duplicates it. **Not run this
    session, explicitly out of scope per the confirmed prompt:** root
    `make validation-report` — this step changes observability/contract and its
    tests only, not provisioning behaviour.
    Commit: see `git log` for `feat(AUTHZ-07): expose platform import outcomes
    in activity` on branch
    `1986-authz-07-root-platform-admin-bootstrap-and-declarative-platform-provisioning`.
  - Close-out hardening pass, same day (2026-07-14), same issue #1912 / PR
    #1957 — four findings re-derived from the code and fixed: (1) the
    frontend no longer rebuilds the import `TaskTarget` itself —
    `ImportLaunchResponse` gained a `target: TaskTarget` field returned
    verbatim from `_import_target()`; `launchPlatformImport.ts::buildImportTarget`
    and `IMPORT_TARGET_TYPE` are deleted, `launchPlatformImport()` returns the
    backend's own `target`, and `MigrationPage.tsx::handleLaunch` registers
    that value directly — one canonical target, not two independently-built
    ones (backend test asserts `launch["target"] == task["target"]`
    verbatim). (2) `taskTypes.ts`'s hand-maintained `MigrationResult` mirror
    is deleted; `MigrationTaskEvent.detail.result` now imports the generated
    `MigrationResult` from `controlPlaneOpenApi.ts` — the SSE adapter itself
    stays hand-maintained (still no generated `TaskEvent` union to draw from,
    per the RFC note above it), but this one field IS on the OpenAPI schema
    and no longer duplicated by hand. (3) `TaskActivity.tsx`'s counter
    disclosure previously omitted every `*_skipped` counter and
    `users_processed`, so a partial reconciliation with skips but no warning
    text could still read as a clean, uninspectable success; the display list
    now covers all fifteen numeric `MigrationResult` counters, and
    `hasMigrationWarnings`/`MigrationResultDetails` default `warnings` to `[]`
    to handle the generated type's now-optional field without a runtime
    crash on an older/partial payload. (4) doc convergence: this file's Step
    2 "Not yet live-verified" sentence (stale — the exit gate above already
    records the 2026-07-14 live validation) is removed; `id-legend.yaml`'s
    AUTHZ-07 note updated; `docs/swift/ux/COMPONENT-UX.md` gained a
    `TaskActivity` entry; `CONTROL-PLANE-PRODUCT-CONTRACT.md` gained a dated
    §16 entry for `TaskSummary.detail` / `ImportLaunchResponse.target`.
    Tests: backend — two assertions added to
    `test_import_export_task_observability.py` proving the launch response
    and persisted task carry the identical target; frontend —
    `TaskActivity.test.tsx` gained a test asserting a non-zero
    `team_roles_skipped`/`agents_skipped`/`users_processed` counter renders.
    Verified offline: targeted backend/frontend suites, `make
    update-control-plane-api` regenerated `controlPlaneOpenApi.ts`,
    `tsc --noEmit`/`prettier --check` clean, `make code-quality` clean in both
    touched projects. Commit: see `git log` for `fix(AUTHZ-07): converge
    platform import observability contract` on the same branch.

- [x] **Step 4 — finish the pure-infrastructure factory boundary.** In
      `fred-deployment-factory`, remove nominative/demo users and legacy app
      roles from realm templates; make preflight/tests assert zero users; remove
      stale factory validation targets and links now owned by `fred/validation`;
      explicitly delete or time-bound the direct OpenFGA migration script.
  - Exit gate: factory starts identity/authz infrastructure with no Fred business
    population; registration → bootstrap → Fred import is the only tested path.
    **Met — live-validated 2026-07-15.**
  - Result: `fred-deployment-factory` commit `05dda9e`
    (`refactor(AUTHZ-07): make deployment factory infrastructure-only`) plus
    correction commit `65090fd` (`fix(AUTHZ-07): align factory preflight with
    identity-only realm`). Scope: tracked Keycloak realm templates now carry
    zero users and zero groups; the legacy application user roles
    `app:admin`/`app:editor`/`app:viewer` are removed; `app:service_agent` is
    kept for M2M service accounts; service accounts are created dynamically
    and provisioned by the post-install hooks rather than templated; the k3d
    OpenFGA seed is removed; the direct `fredlab-authz-migrate-swift.py`
    script is deleted; the factory's own validation targets are removed,
    validation ownership moving entirely to `fred/validation`; preflight now
    requires `service_agent` and rejects `admin`/`editor`/`viewer`. Verified
    offline: the `check-pure-infrastructure` guard, `helm lint`/`helm
    template`, `docker compose config`, `bash -n`, and the OpenFGA sync all
    green. Live-validated 2026-07-15: a full from-scratch restart against the
    resulting empty factory succeeded end to end — Alice self-registered in
    Keycloak, submitted the one-time bootstrap secret, became the first
    `platform_admin`, entered Fred, and imported the
    demo-provisioning-bundle successfully. The only tested path is therefore
    empty factory → registration → Fred bootstrap → Fred import, confirming
    the exit gate.

- [ ] **Step 5 — package one fresh-install path for k3d, GKE and AKS.** Wire
      the externally supplied bootstrap secret through the existing
      Helm/Kubernetes Secret mechanisms, without committing or logging it. The
      canonical Fred chart owns one portable application contract
      (`bootstrap_token_env_var` plus `secretKeyRef`); each platform overlay
      supplies only the existing Secret name/key through its classification's
      secret source. Do not create a cloud-specific bootstrap implementation,
      a second chart, a migration command, or compatibility code for a Swift
      installation predating the durable marker.
  - **Delivery decision confirmed 2026-07-15:** today's two targets are new
    platforms, one on GKE and one on AKS. AUTHZ-07 therefore supports a clean
    installation only. The sole data migration in scope is **KEA → fresh Swift**:
    export KEA, deploy empty Swift infrastructure/application, self-register the
    first identity, complete root bootstrap, then use Fred's canonical platform
    import. There is no Swift → Swift in-place-upgrade contract to invent in
    this candidate.
  - Implementation order for today's critical path:
    1. add the portable existing-Secret reference to the canonical Fred chart
       and set `app.bootstrap_token_env_var` to its environment-variable name;
    2. wire the GKE overlay to its existing C1 Foundation Secret and git-ignored
       values source;
    3. wire the AKS overlay to the same chart contract and its existing C2
       Secret source — values only, no forked templates;
    4. prove with `helm lint`/`helm template` that both workloads render the
       same Control Plane contract, contain only `secretKeyRef`, never a secret
       value or `bootstrap_token_file`, and fail closed when the reference is
       absent or invalid;
    5. perform one fresh-install smoke path per cloud: empty services → user
       registration → authenticated secret submission → first
       `platform_admin` → declarative import → teams visible →
       `make validation-report`.
  - Exit gate: one chart contract works unchanged on GKE and AKS; tracked files
    contain no bootstrap-secret value; both rendered deployments use an
    obligatory Secret reference; both fresh installations complete bootstrap
    and import; no Swift-upgrade compatibility path was added.
  - Execution: issue #1912 / PR #1957 / branch
    `1986-authz-07-root-platform-admin-bootstrap-and-declarative-platform-provisioning`.
  - Claude prompt/result/commit: pending this recadrage.

- [ ] **Step 6 — final convergence and UX hardening.** Remove the superseded
      config-seeded platform-role path and any remaining parallel vocabulary;
      decide and implement durable/recoverable execution for the canonical
      import; close bootstrap-page responsive, truncation, semantic-form and
      accessibility gaps; align RFCs, generated contracts, backlog and PMO.
  - Exit gate: one owner per bootstrap/provisioning concept, full root quality
    and offline tests green, live `make validation-report` green, manual UI pass
    recorded, and no stale factory/script/documented alternative remains.
  - Observed live, 2026-07-15 (during Step 4's validation run, no fix applied
    here): after the demo-provisioning-bundle import succeeded, the Teams
    page Alice already had open did not show the newly imported teams until
    she manually refreshed. The import task's own terminal state and the
    Activity page were both correct; the team list appears to still be
    serving a stale RTK Query cache because import-task completion does not
    invalidate/refetch the team-list query. To be re-derived against the
    current code and fixed in Step 6, with a test proving the team list
    updates automatically — no full page reload, no second parallel store.
  - Claude prompt/result/commit: pending Step 5.

- [ ] Swift launch: build readiness-report endpoint reading live OpenFGA tuples (RFC §24.8 — no durable audit-log store exists yet; follow-up, not a launch blocker).
- [x] **Item 8b watch item materialized live and closed (2026-07-13, same PR #1957 / issue #1912, mechanical regression fix, no new ID).** The item-8b know scope note above ("believed low-risk but not exhaustively proven") turned out to matter: the browser self-test (item 17, run by Alice) reproduced the regression exactly as flagged — 14 steps passed (personal folder creation, document indexing, self-test agent enrollment, prompt/session creation), then all four direct runtime execution calls failed HTTP 403 (`Ask the agent (ALPHA)`, `Ask the agent (BETA)`, `Verify the system prompt`, `Verify the marketplace prompt`); fixture teardown still succeeded. Root cause confirmed: removing `groups_list_to_relations`/`_user_contextual_relations` (this item) correctly dropped the Keycloak-groups-derived `team_member` relation, but the same helper also carried the *other*, non-Keycloak contextual relation it built — `user:<uid> team_member team:personal-<uid>` — which the runtime's OpenFGA `CAN_READ` check on `personal-<uid>` had always silently depended on, since that relation was never a persisted tuple. Fix: `libs/fred-runtime/fred_runtime/app/agent_app.py::_authorize_execution_or_raise` now special-cases a personal space (`is_personal_team_id`/bare `"personal"`) **before** the OpenFGA branch — authorized by exact identity comparison against `fred_core.common.personal_team_id(authenticated_user.uid)` (audited `personal_space_owner_authorized`), any other personal-space id or the bare alias explicitly denied (audited `personal_space_denied`, HTTP 403, never reaching OpenFGA). Collaborative teams are untouched: still the same OpenFGA `CAN_READ` check, still fail-closed. `service_agent` execution is untouched (checked first, returns before the personal-space branch). **No Keycloak-groups fallback of any kind was restored** — this is a runtime-local identity check, not a relation derived from `groups`, a JWT claim, or a role. New tests in `libs/fred-runtime/tests/test_agent_app.py`: owner-authorized-without-OpenFGA, other-user's-personal-space-denied-even-when-OpenFGA-would-allow, bare-`"personal"`-alias-denied — all alongside the pre-existing collaborative-allow/deny and `service_agent` coverage. Verified offline: fred-runtime 420 passed (12 in the authorization block), `make code-quality` clean (ruff, bandit, basedpyright). Documented in `RUNTIME-EXECUTION-CONTRACT.md` §2.2 and a new dated entry at the top of that file. Not yet re-run live: `fred-deployment-factory` `make validation-report` and the UI self-test, both tracked as the next step in `NOTES-AUTHZ05-REVIEW.md`.
- [x] Developer confirmation on this addendum (2026-07-09, second pass — naming decision, §25a scope, and bootstrap-endpoint shape all explicitly confirmed before implementation); continuing under existing GitHub issue #1912 / PR #1957 (CLAUDE.md Step 3/3.5 — no new issue needed).
