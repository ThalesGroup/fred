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
- [x] `knowledge-flow model/controller.py` umap (zero-authz) → `TagPermission.READ`/`UPDATE`
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
- [ ] Switch the admin branch of `require_task_access` / ownership to `CAN_MANAGE_PLATFORM`
- [ ] Anti-regression: `grep @authorize|authorize_or_raise|require_admin|is_authorized` outside `tests/` returns 0 app hits
- [ ] `make code-quality` + `make test` green across touched packages

---

## Progress

| Item | Status |
| ---- | ------ |
| AUTHZ-02 schema + enums | ✅ done (48 security tests green; dedicated org-perm tests TODO) |
| AUTHZ-03 Bucket C (org-level global/admin) | ✅ done (both backends; ruff green) — except 2 service-layer admin methods |
| AUTHZ-03 Bucket A (instance) | in_progress (content, model umap, scheduler/process-library done; ingestion, evaluations, audio, scheduler/process-documents pending) |
| AUTHZ-03 Bucket B (collections) | not started |
| AUTHZ-04 teardown | not started (atomic, last) |
