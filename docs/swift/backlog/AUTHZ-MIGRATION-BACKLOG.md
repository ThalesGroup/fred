# AUTHZ — Full RBAC → ReBAC migration backlog

Track: `AUTHZ-01` (umbrella) · RFC: [RBAC-TO-REBAC-MIGRATION-RFC](../rfc/RBAC-TO-REBAC-MIGRATION-RFC.md)
Owner: Simon · Status registry: [id-legend.yaml](../data/id-legend.yaml) · PMO: [PMO-BOARD.md](../PMO-BOARD.md)
Execution: GitHub issue #1875

Goal: a single authorization model — **ReBAC only**. Remove all RBAC
(`@authorize`, `authorize_or_raise`, `is_authorized`, `require_admin`); cover every endpoint with ReBAC,
adding only `check_user_permission_or_raise` / `check_user_team_permission_or_raise` / `lookup_user_resources`.
Ownership checks (`require_task_access`, session/checkpoint ownership) are **kept** (not RBAC).

---

## AUTHZ-02 — Org-level schema extension + enums
- [ ] Add fine-grained permissions to the `organization` type in `schema.fga`
      (`can_read_kpi/logs/metrics/opensearch/knowledge_graph` → viewer ;
       `can_administer_users`, `can_manage_platform`, `can_run_benchmark` → admin)
- [ ] Regenerate `schema.fga.json` (`cd libs/fred-core && make transform-openfga-schema`)
- [ ] Add `DocumentPermission.PROCESS` + new `OrganizationPermission` members in `rebac_engine.py`
- [ ] Unit tests for the new org-level permissions (viewer reads, admin manages, no-role denied)

## AUTHZ-03 — Endpoint migration (buckets A/B/C)

### Bucket A — instance-scoped (`check_user_permission_or_raise`)
- [ ] `knowledge-flow content_service.py` (5 reads) → `DocumentPermission.READ` / `document_uid`
- [ ] `knowledge-flow ingestion_service.py` upload → `TagPermission.UPDATE` per destination tag
- [ ] `knowledge-flow scheduler_controller.py` → `TagPermission.UPDATE` / `DocumentPermission.PROCESS`
- [ ] `knowledge-flow model/controller.py` umap (zero-authz) → `TagPermission.READ`/`UPDATE`
- [ ] `control-plane evaluations/api.py` (zero-authz) → team `CAN_READ`/`CAN_UPDATE_RESOURCES`
      (load `team_id` from the campaign for `campaign_id`-only routes)
- [ ] `knowledge-flow audio_transcription_controller.py` → scope per RFC D3

### Bucket B — collections/search (`lookup_user_resources`)
- [ ] Drop residual `@authorize` on already-ReBAC services (metadata, tabular, vector_search.search, tag list_all_tags)
- [ ] Wire lookup-filtering: `resources list_resources_by_kind`, runtime `list_agents`, `statistic /stat/*`

### Bucket C — org-level (`check_user_permission_or_raise` on `organization:fred`)
- [ ] `neo4j_controller.py` (5) → `CAN_READ_KNOWLEDGE_GRAPH`
- [ ] `kpi/opensearch_controller.py` (23) → `CAN_READ_OPENSEARCH`
- [ ] `kpi/prometheus_controller.py` (9) → `CAN_READ_METRICS`
- [ ] `kpi/kpi_controller.py` (1) + control-plane `kpi/api.py` (zero-authz) → `CAN_READ_KPI`
- [ ] `kpi/logs_controller.py` (1) → `CAN_READ_LOGS`
- [ ] control-plane `users/api.py` CRUD (zero-authz) → `CAN_ADMINISTER_USERS`
- [ ] `import_export/api.py` + `main.py` policies/lifecycle + metadata audit/fix + tags rebac/backfill → `CAN_MANAGE_PLATFORM`
- [ ] `benchmark/controller.py` (5, zero-authz) → `CAN_RUN_BENCHMARK`

## AUTHZ-04 — RBAC teardown
- [ ] Remove `RBACProvider`, `authz_providers`, `authorize` decorator, `authorize_or_raise`, `is_authorized`, `require_admin`
- [ ] Switch the admin branch of `require_task_access` / ownership to `CAN_MANAGE_PLATFORM`
- [ ] Anti-regression: `grep @authorize|authorize_or_raise|require_admin|is_authorized` outside `tests/` returns 0 app hits
- [ ] `make code-quality` + `make test` green across touched packages

---

## Progress

| Item | Status |
| ---- | ------ |
| AUTHZ-02 schema + enums | in_progress |
| AUTHZ-03 endpoint migration | not started |
| AUTHZ-04 teardown | not started |
