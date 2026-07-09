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
      (`can_read_kpi/logs/metrics/opensearch/knowledge_graph` → viewer ;
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
- [x] `neo4j_controller.py` (5) → `CAN_READ_KNOWLEDGE_GRAPH`
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

## AUTHZ-05 — Fred-owned target authorization model + compatibility bridge  ⏳ PROPOSED

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
- [x] Swift launch: add `platform_admin`/`platform_observer` relations + config-seeded bootstrap (RFC §24.3). Implemented 2026-07-09, additive only (legacy `admin`/`editor`/`viewer` capabilities unchanged for now).
- [x] Deliberate, narrow exception: `can_administer_owners`/`can_administer_managers` also accept `platform_admin from organization` (not legacy `admin`), so a freshly created team still gets its first owner/manager assigned — otherwise the escalation fix breaks team bootstrap (`docs/swift/platform/REBAC.md` "locked design authority": team creation and manager assignment belong to the platform admin). Nothing else escalates. Verified live against a real OpenFGA instance (`fred_core/tests/integration/test_rebac.py`), not just offline schema assertions.
- [ ] **New finding (2026-07-09, not yet fixed):** `OrganizationPermission.CAN_READ_CONTENT`/`CAN_PROCESS_CONTENT` (~30 call sites across knowledge-flow-backend: ingestion, vector search, corpus manager, statistics, scheduler, audio, report) are org-scoped, not team-scoped — any Keycloak `editor` can read/process any team's content today. See RFC §25a. This is a larger, separate audit of ~9 controllers — tracked here, not bundled into the launch-safety fix.
- [ ] Swift launch: one-time translation of existing Keycloak admin/editor/viewer holders and stored team owner/manager tuples into target relations (RFC §18, §24.1).
- [ ] Team-role vocabulary rename (`owner`→`team_manager`, `manager`→`team_editor`, +`team_analyst`) across `teams/schemas.py`, `teams/service.py` (3 endpoints + owner-safety invariant), `evaluations/api.py` (`CAN_RUN_EVALUATIONS`), frontend `TeamSettingsMembersTable.tsx`, and generated OpenAPI client. Deferred from the 2026-07-09 pass — real lift, not required to close the platform/team visibility gap (that's fixed by the schema.fga change above).
- [ ] Swift launch (deployment task, not code): populate `platform_admin_subjects`/`platform_observer_subjects` in the swift deployment config (`fred-deployment-factory`) with the known existing admin/viewer population — the config field itself and the startup bootstrap logic are implemented (RFC §24.3), only the real subject list is still an operational step.
- [ ] Swift launch: build readiness-report endpoint reading live OpenFGA tuples (RFC §24.8 — no durable audit-log store exists yet; follow-up, not a launch blocker).
- [ ] Developer confirmation on this addendum, then GitHub issue for implementation (CLAUDE.md Step 3/3.5).
