# RFC — Full RBAC → ReBAC migration (eliminate role-based authorization)

**Status:** Active (confirmed 2026-06-29)
**Author:** Simon Cariou
**Date:** 2026-06-29
**Task ID:** `AUTHZ-01` (new domain code `AUTHZ` registered in `CLAUDE.md` §Task IDs + `id-legend.yaml`)
**Area:** `fred-core` (security), `apps/knowledge-flow-backend`, `apps/control-plane-backend`, `libs/fred-runtime`
**Touches:** `libs/fred-core/.../security/rebac/schema.fga` (+ generated `schema.fga.json`),
`rebac_engine.py` (enums), removal of `security/rbac.py` + `authorization_decorator.py` + the RBAC clauses of
`security/authorization.py`. No HTTP contract field changes (authz is enforcement-side).

> Relationship to `RUNTIME-07` (`EXECUTION-GRANT-SECURITY-HARDENING-RFC.md`): that RFC made the **runtime
> pods** authorize execute/stream/resume via pod-side OpenFGA. This RFC generalizes the same principle —
> *OpenFGA/ReBAC decides authorization, everywhere* — by removing the **remaining RBAC** still used on
> non-execution endpoints across all three backends. It does not alter the runtime execution path.

---

## 1. Problem

Authorization is enforced by **two** parallel systems:
- **ReBAC** (target) — `check_user_permission_or_raise`, `check_user_team_permission_or_raise`,
  `lookup_user_resources` against OpenFGA, per-instance / per-scope.
- **RBAC legacy** — `@authorize(Action, Resource)`, `authorize_or_raise`, `is_authorized`, `require_admin`,
  driven by a static role→resource→action matrix (`RBACProvider`). Coarse (role/type level, no instance).

Maintaining both is a security liability: divergent decisions, endpoints protected at the type level only
(any editor can read *any* document), and a non-trivial surface where the two disagree. An audit of the three
backends found the RBAC surface to be: **78** `@authorize`, **61** `authorize_or_raise`, **20**
`require_admin`, **2** `is_authorized` (≈20 files), plus a set of endpoints with **no authorization at all**.

**Goal:** a single authorization model — **ReBAC only**. Remove all RBAC; cover every endpoint with ReBAC,
adding *only* `check_user_permission_or_raise` / `check_user_team_permission_or_raise` / `lookup_user_resources`
(no new integration mechanism).

## 2. Root cause of the schema gap

ReBAC types in `schema.fga` are `user, organization, team, agent, tag, document, resource`. The RBAC
`Resource` enum is much wider (KPIS, LOGS, METRICS, OPENSEARCH, NEO4J, FILES, FEEDBACK, SESSIONS, …). The
content/collaboration resources map onto existing ReBAC types; the **global infrastructure / admin** resources
have **no ReBAC type and no resource instance** to check. Their natural scope is the **singleton
`organization:fred`**, whose `admin/editor/viewer` relations are already populated from Keycloak roles
(`user_role_to_organization_relation`). The schema simply lacks *permissions* on that type.

## 3. Proposed solution

### 3.1 Additive schema extension (only change to `schema.fga`)
Add permissions to the **existing** `organization` type (no new type, no relation changes). Defaults chosen to
**preserve current `rbac.py` behavior** (viewer reads everything; admin manages):

```fga
type organization
  relations
    define admin: [user]
    define editor: [user] or admin
    define viewer: [user] or editor

    # existing
    define can_create_team: admin
    define can_create_agent: editor
    define can_edit_agent_class_path: admin

    # NEW — global-infra reads (viewer)
    define can_read_kpi: viewer
    define can_read_logs: viewer
    define can_read_metrics: viewer
    define can_read_opensearch: viewer
    define can_read_knowledge_graph: viewer   # Neo4j (explicitly NOT admin-only)

    # NEW — platform administration (admin)
    define can_administer_users: admin
    define can_manage_platform: admin         # import/export, policies/purge, lifecycle, store audit/fix, rebac backfill
    define can_run_benchmark: admin
```

### 3.2 Python enum additions (`rebac_engine.py`) — `.fga` relations already exist
- `DocumentPermission.PROCESS = "process"` (relation `document#process` already in schema).
- `OrganizationPermission`: add `CAN_READ_KPI`, `CAN_READ_LOGS`, `CAN_READ_METRICS`, `CAN_READ_OPENSEARCH`,
  `CAN_READ_KNOWLEDGE_GRAPH`, `CAN_ADMINISTER_USERS`, `CAN_MANAGE_PLATFORM`, `CAN_RUN_BENCHMARK` (and, for
  completeness, the already-defined `CAN_CREATE_TEAM`, `CAN_CREATE_AGENT`).

`check_user_permission_or_raise(user, OrganizationPermission.X, ORGANIZATION_ID)` (`ORGANIZATION_ID = "fred"`)
then gates global endpoints; `require_admin` sites map to the matching `admin`-level org permission.

### 3.3 Endpoint migration by bucket
- **A — instance-scoped** (existing schema suffices): `content_service.py` (`DocumentPermission.READ`),
  `ingestion_service.py` upload (`TagPermission.UPDATE` per destination tag), `scheduler_controller.py`
  (`TagPermission.UPDATE`/`DocumentPermission.PROCESS`), `model/controller.py` umap (`TagPermission`,
  currently zero-authz), control-plane `evaluations/api.py` (team `CAN_READ`/`CAN_UPDATE_RESOURCES`, currently
  zero-authz; load `team_id` from the campaign for `campaign_id`-only routes), `audio_transcription` (arbitrate
  team vs org scope).
- **B — collections/search** via existing `lookup_user_resources`: most are **already** ReBAC at the service
  layer (`metadata`, `tabular`, `vector_search.search`, `tag list_all_tags`) → just drop the residual
  `@authorize`. To wire: `resources list_resources_by_kind`, runtime `list_agents`, `statistic /stat/*`.
- **C — org-level** (uses §3.1): neo4j, opensearch, prometheus/metrics, kpi (kf + cp), logs, users CRUD,
  import/export, policies/lifecycle, store audit/fix, rebac backfill, benchmark.
- **D — already ReBAC / ownership / public** (no change): filesystem (team-scoped; drop redundant
  `authorize_or_raise(FILES)`), runtime execute/evaluate/stream, `tasks` (ReBAC + ownership), `product`;
  ownership (`require_task_access`, session/checkpoint) kept, admin branch → `can_manage_platform`; public
  probes/catalogues unchanged.

### 3.4 RBAC teardown
Once every call site is migrated and a grep proves **zero** application references: delete `RBACProvider`,
`authz_providers`, the `authorize` decorator, `authorize_or_raise`/`is_authorized`/`require_admin`. **Keep** the
`Resource` enum (ReBAC uses `Resource.USER/TEAM/ORGANIZATION/TAGS/DOCUMENTS/RESOURCES/AGENT`); optionally prune
its now-unused members in a follow-up. **Keep** `require_task_access` and ownership checks (not RBAC).

## 4. Alternatives considered
- **Keep RBAC for global/admin endpoints (hybrid).** Rejected by product decision: the goal is a single model.
- **New ReBAC types per global resource** (`type kpi`, `type neo4j`, …). Rejected: no instances exist; it would
  invent a heavier scheme for what is fundamentally an organization-wide capability. Org-level permissions are
  the minimal, idiomatic fit.
- **One coarse `can_administer` / `can_read_global`.** Rejected (default): loses least-privilege; fine-grained
  per-capability permissions are cheap and additive. (Granularity remains the one open RFC decision, §9.)

## 5. Contract impact
None to HTTP request/response schemas (authorization is enforcement-side; denials surface as 403). `schema.fga`
+ generated `schema.fga.json` change; library minor version bump for `fred-core`. No frontend client regen
required (no OpenAPI shape change).

## 6. Migration order (each step green & revertible)
1. Schema + enums (§3.1/§3.2), regenerate `schema.fga.json`.
2. Bucket A → B → C, replacing each RBAC call with the ReBAC equivalent (reuse existing engine wiring).
3. Teardown (§3.4) after zero-reference grep.
Behavior-preserving by construction (org defaults mirror the current role matrix); fail-closed under `c3`
(NoopRebacEngine only in non-OIDC/dev).

## 7. Test plan
- Per migrated endpoint: denied (403/`AuthorizationError`) for an unauthorized principal **and** allowed for an
  authorized one. Extend `tests/security/test_rebac_engine_team_helpers.py`, `test_scoped_area_filesystem.py`.
- Org-level: `viewer` passes global reads; principal without an org role denied; `admin`-only on management.
- Anti-regression guard: `grep` for `@authorize|authorize_or_raise|require_admin|is_authorized` outside
  `tests/` returns 0 application hits after teardown.
- `make code-quality` + `make test` (offline) green in every touched package.

## 8. Backlog & execution
Backlog entry under a new `docs/swift/backlog/AUTHZ-MIGRATION-BACKLOG.md` (or a section in `BACKLOG.md` — see
§9), one sub-item per bucket; `id-legend.yaml` + `PMO-BOARD.md` rows; GitHub issue links RFC + backlog before
implementation (CLAUDE.md Step 3.5).

## 9. Decisions (confirmed 2026-06-29)
- **D1 — Domain code.** ✅ Register new code `AUTHZ` (Authorization model). Added to `CLAUDE.md` §Task IDs and
  `id-legend.yaml` (`AUTHZ-01` umbrella, `AUTHZ-02` schema/enums, `AUTHZ-03` endpoint migration, `AUTHZ-04`
  teardown).
- **D2 — Permission granularity.** ✅ Fine-grained per-capability permissions (§3.1).
- **D3 — `audio_transcription` scope.** Open (low-risk): default organization-level read unless the endpoint
  is found to be team-scoped during AUTHZ-03; decide at implementation of that endpoint.
- **D4 — Backlog location.** ✅ New `docs/swift/backlog/AUTHZ-MIGRATION-BACKLOG.md`.
