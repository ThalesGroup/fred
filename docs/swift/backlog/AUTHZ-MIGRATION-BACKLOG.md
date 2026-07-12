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
- [x] **§25a fixed for the sites where team-scoping is mechanically meaningful** (RFC §27): 9 direct call sites moved from `OrganizationPermission.CAN_READ_CONTENT`/`CAN_PROCESS_CONTENT` to `TagPermission`/`DocumentPermission` on the concrete object (`statistic.list_datasets/set_dataset`, `vector_search.similarity_search/get_visual_evidence_artifact/rerank`, `corpus_manager.build_toc/revectorize/purge`, `scheduler.process_documents`), plus the 15 in-memory statistic calls re-checking the tag authorized at `set_dataset` time. `corpus_manager.capabilities/tasks_get/tasks_result/tasks_list` and `report_controller.write_report` gained a required `team_id`/`tag_id` field (small additive contract change) so they can be team-scoped too — this is what flips the two `xfail` tests in `fred-deployment-factory/validation/scenarios/test_content_scope_bypass.py`. Remaining ~17 sites (audio transcription, fast_markdown/fast_ingest, dummy/echo routes) are genuinely resource-less utilities, left org-scoped and documented as such in `rebac_engine.py` — not a gap.
- [x] **Team-bootstrap problem resolved** (RFC §28, later revised by review item 9 — see below): reading `teams/service.py` in full found there was no team-creation flow at all — a "team" is a Keycloak root group discovered lazily, and `add_team_member` requires the group to already exist, so a freshly created group was unreachable by every membership endpoint. Implemented `POST /teams { name, initial_team_admin_ids }` gated by the existing `can_create_team` capability, one-shot by construction (409 if the team exists — cannot be replayed against an existing team, unlike the reverted `§24.7` attempt). At this point (2026-07-09) it still created a Keycloak group alongside the OpenFGA writes; that step was removed the next day, see review item 9.
- [x] **AUTHZ-05 review, 2026-07-09/10 (`NOTES-AUTHZ05-REVIEW.md`, not the RFC itself — a post-implementation pass triggered by human review of PR #1957).** All code items closed except 8b (blocked on the real production data migration having run — deployment task, not a design question):
  - Items 1a/1b/2/3/4 (independent authz-wiring fixes: prompt-mutation endpoints, agent-template/instance GETs, `/process-documents` empty-tags bypass, platform-stats team scoping, Keycloak-role-derived frontend admin surfaces) and item 6 (deleted the unused, dangerous `authz_migration.py` auto-mapping script) and item 7 (confirmed `team_admin` stays a "super `team_member}`" by design) — all closed 2026-07-09.
  - **Item 5 — `can_create_team` cut from `admin or platform_admin` to `platform_admin`-only.** No other caller in the repo checked this capability against the legacy `admin` relation, so the Keycloak bridge was cut here first, ahead of the wider item 8a removal.
  - **Item 8a — the legacy Keycloak `admin`/`editor`/`viewer` organization relations are removed from `schema.fga` entirely** (2026-07-10): Keycloak is now identity-only, no role bridge of any kind survives. The 5 admin-tier capabilities they used to satisfy (`can_administer_users`, `can_manage_platform`, `can_run_benchmark`, `can_edit_agent_class_path`, `can_read_kpi_global`) are `platform_admin`-only now, same pattern as item 5. The 7 "any connected user" capabilities they used to satisfy (`can_read_content`, `can_process_content`, `can_create_agent`, `can_read_kpi`, `can_read_logs`, `can_read_metrics`, `can_read_opensearch`) never protected anything specific — removed outright, not replaced by another relation; the corresponding endpoints rely on authentication alone.
  - **Item 9 — teams decoupled from Keycloak entirely** (RFC Part 6 §29-32, 2026-07-10): a team is now purely a `team_metadata` row (`id`, `name`) plus its OpenFGA relations — `POST /teams` no longer creates a Keycloak group (generates `uuid4().hex` instead), `list_teams`/`get_team_by_id`/`list_team_members`/`add_team_member`/`remove_team_member`/`update_team_member` make zero Keycloak calls. 3 new platform-admin-only, registry-governance-only capabilities added: `can_list_all_teams` (`GET /teams/all`), `can_delete_team` (`DELETE /teams/{team_id}`), `can_rescue_team_admin` (`POST /teams/{team_id}/rescue-admin` — writes a `team_admin` tuple only if the team currently has zero `team_admin`, the guard that keeps it structurally different from the reverted `§24.7` escalation).
  - **Item 8b — still blocked, not touched.** `groups_list_to_relations`'s `for group in user.groups` loop (the JWT `groups`-claim-derived `team_member` fallback) is today's only source of `team_member` for a user on a team that existed before this branch. Removing it before `fredlab-authz-migrate-swift.py` has run against real production data and written the explicit tuples would drop everyone's team access instantly. Requires explicit reconfirmation at execution time, not just the 2026-07-09 verbal confirmation already on record.
  - Verified end-to-end: fred-core, control-plane-backend, knowledge-flow-backend, fred-runtime offline suites green, `make code-quality` clean on all four, frontend `tsc`/`prettier` clean, Alembic migration upgrade/downgrade verified.
- [x] **Live-campaign findings, 2026-07-11 (`NOTES-AUTHZ05-REVIEW.md` items 10-11, found while standing up the `fred-deployment-factory` validation campaign — not the RFC itself):**
  - **Item 10 — `promote_prompt` cross-team write gap.** Only the source team was permission-checked; the target team was never resolved, letting a `team_editor` copy a prompt's text into any `team_id`, including one they held no relation to. Fixed: resolve the target team under the same `CAN_UPDATE_RESOURCES` requirement as the source. Locked by a live regression scenario in `fred-deployment-factory/validation/scenarios/test_prompt_authz.py` plus a unit wiring test.
  - **Item 11 — dead second frontend permission system.** `usePermissions()`/`PermissionSummary.items` (Keycloak-role-derived) sat alongside the correct OpenFGA-derived `useUserCapabilities()`. Since AUTHZ-05 removed Keycloak app roles, `items` had gone permanently empty, silently disabling 6 routes and 3 in-page controls for **everyone, including `platform_admin`**. Replaced with one two-tier hook pattern (`useUserCapabilities` org-level / `useTeamCapabilities` team-level), documented in the new `docs/swift/platform/FRONTEND-AUTHZ-PATTERN.md`; `PermissionSummary` shrunk to its two OpenFGA-derived booleans (`CONTROL-PLANE-PRODUCT-CONTRACT.md` §14). Also added a live "authorization self-test" to `/admin/self-test` (runs against the current admin's own session or any other account via Keycloak direct-grant, dev/test realms only) so "does the UI honor the model" is a self-service, in-browser answer going forward, not just a manual checklist.
  - New live scenario files added to `fred-deployment-factory/validation/scenarios/`: `test_prompt_authz.py`, `test_team_registry_authz.py`, `test_platform_admin_capabilities.py` — 215 live assertions total.
  - Verified: fred-core 262 passed/1 skipped, control-plane-backend 264 passed, frontend 326 passed + `tsc`/`prettier` clean, `make code-quality` clean.
- [x] **Live-campaign findings, 2026-07-11 continued (`NOTES-AUTHZ05-REVIEW.md` items 12-16, found running the manual persona-by-persona pass against the live `fred-deployment-factory` stack):**
  - **Item 12 — `GET /teams/all` leaked the caller's own personal space into the registry.** Not a cross-tenant leak (verified: `platform_admin` read only their own personal prompts), but a false positive in the new authz self-test. `list_all_teams_for_registry` now filters `personal-*` ids out of `list_all_teams_unfiltered`'s result.
  - **Item 13 — `Protected` (item 11's route guard) redirected to `/unauthorized` before `/frontend/bootstrap` had loaded**, on every hard refresh, with no way back. `useUserCapabilities()` now relays `isLoading`; `Protected` waits for it before deciding.
  - **Item 14 — platform-wide member/admin counts silently showed 0 on "Données plateforme".** `compute_platform_stats` called the permission-checked `list_team_members` with the caller's own identity, which 403s on every real team a `platform_admin` isn't personally a member of (the common case). New `list_team_members_unfiltered` (same contract as item 3's `list_all_teams_unfiltered`) bypasses the per-team check.
  - **Item 15/16 — `platform_observer` had no reachable KPI dashboard, and `/admin/analytics` was wrongly admin-only.** A first attempt widened `/admin/analytics`'s route guard alone, which still 403'd against the backend (`can_read_kpi_global`, platform_admin-only). Root cause: `can_read_kpi_global` was a legacy (`Action.READ_GLOBAL`) capability, separate from the RFC's actual target vocabulary (§6.1 defines only `can_observe_platform` for this purpose) — introduced as an admin-tier capability by item 8a and never reconciled with `can_observe_platform`. Per explicit product decision (Dimitri, 2026-07-11): today `platform_admin` and `platform_observer` see the same platform-wide recap; only `platform_admin` sees the other `/admin/*` pages (team registry, task activity, platform data, self-test). Resolution: `can_read_kpi_global` retired from `schema.fga` entirely; the 10 Analytics preset endpoints (`control-plane-backend/kpi/presets/*.py`) and the standalone KPI dashboard (`/monitoring/kpis`) both now check `can_observe_platform`. `/admin/analytics` requires `observer`; a new capability-aware `AdminIndexRoute` sends a `platform_admin` to `/admin/teams` and a `platform_observer`-only user to `/admin/analytics`. When the Analytics dashboard grows admin-only technical panels, gate those specific widgets on a new, narrower capability instead of resurrecting the old split.
  - Verified: fred-core, control-plane-backend, knowledge-flow-backend offline suites green, `make code-quality` clean on all three, frontend `tsc`/`prettier`/`vitest` clean. `schema.fga.json` regenerated.
  - **Item 17 — authorization self-test enriched with a real write probe.** The browser self-test (`/admin/self-test`) only ever checked denials (isolation) — no step proved that a *granted* write permission actually works. New `team-write-access` step: reads the target account's own `permissions` on their first team (`GET /teams/{id}`), attempts a real, run-scoped, immediately-cleaned-up prompt create, and asserts the result matches `can_update_resources`. Frontend-only, `authzProbeScenario.ts`/`useAuthzProbeRun.ts`, 10 new unit tests.
- [x] **AUTHZ-06 — Cumulative team roles (RFC Part 7, `docs/swift/rfc/FRED-AUTHORIZATION-TARGET-MODEL-RFC.md` §33-39), code-complete 2026-07-12.** A user may hold `team_admin`+`team_editor`+`team_analyst` on the same team simultaneously — `update_team_member` used to enforce exactly one role per user per team, making the common small-team shape (one person governs, edits, and evaluates; a few plain members) structurally unreachable. `schema.fga`: **no change** — OpenFGA already permits multiple relation tuples per user per object; the exclusivity was a service-layer convention only. `update_team_member`/`PATCH /teams/{team_id}/members/{user_id}` retired, replaced by `grant_team_member_role`/`POST .../roles` and `revoke_team_member_role`/`DELETE .../roles/{relation}` — one role granted or revoked per call, same per-role permission checks as today, revoke refuses to empty a member's last role. Contract change: `TeamMember.relation` (singular) → `relations` (list) — `CONTROL-PLANE-PRODUCT-CONTRACT.md` §15. `TeamSettingsMembersTable.tsx` reworked to independent per-role toggle chips. Verified: control-plane-backend 275 passed (9 new), `make code-quality` clean; frontend `tsc`/`prettier`/`vitest` (345 passed) clean. Design updated in `docs/swift/platform/REBAC.md`. **Not yet done: the live validation campaign** (`make validation-report`, deployment-factory test profiles, manual UI pass, campaign registry) — tracked in `NOTES-AUTHZ05-REVIEW.md`. Continuing under existing GitHub issue #1912 / PR #1957, same branch.
- [ ] Swift launch (deployment task, not code): populate `platform_admin_subjects`/`platform_observer_subjects` in the swift deployment config (`fred-deployment-factory`) with the known existing admin/viewer population — the config field itself and the startup bootstrap logic are implemented (RFC §24.3), only the real subject list is still an operational step.
- [ ] Swift launch: build readiness-report endpoint reading live OpenFGA tuples (RFC §24.8 — no durable audit-log store exists yet; follow-up, not a launch blocker).
- [ ] Swift launch (deployment task, not code): confirm `fredlab-authz-migrate-swift.py` has run against real production data before removing the `groups_list_to_relations` Keycloak-groups-claim fallback (review item 8b) — the code change itself is a one-line removal, already scoped, just gated on this confirmation.
- [x] Developer confirmation on this addendum (2026-07-09, second pass — naming decision, §25a scope, and bootstrap-endpoint shape all explicitly confirmed before implementation); continuing under existing GitHub issue #1912 / PR #1957 (CLAUDE.md Step 3/3.5 — no new issue needed).
