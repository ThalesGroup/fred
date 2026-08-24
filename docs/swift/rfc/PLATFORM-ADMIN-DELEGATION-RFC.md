# RFC — Platform-admin delegation with a protected bootstrap root

**Status:** Accepted unilaterally — model decided by the developer on 2026-08-21: any
`platform_admin` may grant and revoke `platform_observer`; **the
`platform_admin` role itself is granted and revoked by the bootstrap root
only**; the bootstrap identity can never be revoked.

**Author:** Simon Cariou

**Date:** 2026-08-21

**Area:** `control-plane-backend` (users surface); `frontend` admin UI (new
"Platform roles" entry in the admin sidebar) — both in this RFC's scope

**Related:** `docs/swift/platform/REBAC.md` (platform roles),
`docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md`,
`control_plane_backend/bootstrap/service.py` (AUTHZ-07 root bootstrap)

---

## 1. Problem

`platform_admin` / `platform_observer` are stored OpenFGA tuples on
`organization:fred`. Today exactly three writers exist in the codebase: the
one-shot, self-promotion-only bootstrap endpoint (AUTHZ-07), the kea→swift
migration reconciliation (`kea_reconciliation.py`), and the bundle importer
(`importer.py`). There is **no product surface** to grant or revoke a
platform role.

`REBAC.md` already says platform roles are granted "via the root bootstrap
endpoint **or explicit admin action**" — but that admin action has no
implementation; in practice it is a raw OpenFGA tuple write by an operator
(`fga tuple create/delete`), which requires cluster access.

Concrete operational trigger (prism prod, 2026-08-21): the kea→swift
migration granted `platform_admin` to every legacy Keycloak realm-role
`admin`. Cleaning that up requires kubectl/OpenFGA surgery today. And any
admin appointed going forward must never be able to revoke the bootstrap
super-admin.

## 2. The two roles this surface manages

Reference: `REBAC.md` (authority). Summary of each role's reach, so the
grant/revoke semantics below are unambiguous:

- **`platform_admin`** — administration: user administration
  (`can_administer_users`), platform management — import/export/reset
  (`can_manage_platform`), team-registry governance (`can_create_team`,
  `can_list_all_teams`, `can_delete_team`, `can_rescue_team_admin`), agent
  class-path editing, plus everything `platform_observer` sees (union). No
  implicit team-content rights: team-scoped writes still require an explicit
  team role.
- **`platform_observer`** — observation only, zero write access. Exactly one
  computed capability, `can_observe_platform`, which gates: the control-plane
  Analytics presets with platform-wide scope (`GET
  /control-plane/v1/kpi/presets/*` — an observer sees the platform-wide KPI
  recap instead of only their own activity) and the raw OpenSearch Ops
  surface in knowledge-flow (cluster health, indices, mappings, shards). It
  grants no user administration, no team-registry action, no platform
  management, and no team-content right of any kind. The kea→swift migration
  maps the legacy `viewer` realm role to this relation.

## 3. Proposed solution

Model: **root-managed admins, delegated observers**.

1. Three new control-plane endpoints, mirroring the team-role pattern
   (`POST /teams/{team_id}/members/{user_id}/roles`,
   `DELETE …/roles/{relation}`):
   - `GET /users/platform-roles` — list current `platform_admin` /
     `platform_observer` holders (tuples read from OpenFGA), for the admin
     UI and for auditing. Response: one entry per holder (`UserSummary` +
     its relations + `is_bootstrap_root` flag) plus a top-level
     `caller_is_bootstrap_root` convenience flag for the UI.
   - `POST /users/{user_id}/platform-roles` — body `{relation}` where
     relation ∈ {`platform_admin`, `platform_observer`}.
   - `DELETE /users/{user_id}/platform-roles/{relation}`.
2. All three gated on the existing
   `OrganizationPermission.CAN_ADMINISTER_USERS` (held by `platform_admin`
   only). **No new relation, no OpenFGA schema change.**
3. Grant/revoke semantics — explicit, both relations, both directions:
   - Any `platform_admin` may **grant and revoke `platform_observer`** on
     any user. Observer tuples carry no special protection.
   - **Granting and revoking `platform_admin` are both reserved to the
     bootstrap root** (the uid recorded in
     `platformbootstrap.completed_by`). Appointed `platform_admin`s cannot
     appoint other admins, cannot revoke each other, and cannot drop their
     own admin role — the admin population is managed exclusively by the
     root. One rule, no exceptions.
   - The **bootstrap root is itself a `platform_admin`** (same relation, no
     separate role). Its two distinctions are service-layer rules, not a
     schema construct: sole manager of the `platform_admin` population, and
     itself unrevocable.
4. Protection rules (service layer) on `…/platform-roles/platform_admin`,
   both `POST` and `DELETE`:
   - the caller must be the uid recorded in
     `platformbootstrap.completed_by` — any other `platform_admin` gets an
     explicit 403;
   - on `DELETE`, the target must additionally not be that same
     `completed_by` uid — refused with an explicit 403 for every caller,
     **including the root itself** (root self-demotion is irreversible
     because bootstrap never reopens; refuse it outright);
   - if bootstrap has never run (`platformbootstrap` row absent — e.g. a
     platform populated only by a migration import), both routes refuse
     with an explicit 409: no root exists yet, run
     `POST /bootstrap/platform-admin` first (still open by definition in
     that state, since the marker is what closes it).
   The `platform_observer` routes carry neither restriction.
   Anchor precedent: `PlatformBootstrapStore.get_completed_by()` already
   serves exactly this purpose for `POST /reset-rebac` — the teardown flow
   preserves that identity "regardless of who calls it"
   (CONTROL-PLANE-PRODUCT-CONTRACT.md §27), and the row is "never deleted
   by any product code path" (store docstring). This RFC reuses the same
   accessor and the same durable row — no second source of root identity.
5. No minimum-admin count is enforced: once bootstrap has run, the
   protected root is always present by construction.
6. Grants/revocations go through the ReBAC engine with `actor_uid` set, so
   they land in the audit trail like every other relation change.
7. Admin UI — a new **"Platform roles"** entry in the admin sidebar
   (`AdminNavbar`) opening `pages/admin/PlatformRolesPage`:
   - table of current holders: user identity (`UserSummary`), relations
     held, and a visible badge on the bootstrap root's row
     (`is_bootstrap_root`);
   - grant flow: pick a user (reusing the `GET /users` admin list) and a
     relation; revoke flow: per-row action;
   - visibility rules mirror the backend (display-only — the backend
     enforces): `platform_observer` grant/revoke shown to any
     `platform_admin`; `platform_admin` grant/revoke shown only when
     `caller_is_bootstrap_root`; no revoke action ever shown on the root's
     row;
   - consumes only the generated RTK Query hooks
     (`controlPlaneOpenApi.ts`), per the generated-client rule; follows
     `FRONTEND_CODING_GUIDELINES.md` (mandatory under `rework/`).

## 4. Alternatives considered

- **New `platform_root` relation in the OpenFGA schema** (model-level
  guarantee): rejected for now — schema migration, bootstrap change, and a
  tuple migration on every existing deployment, against the consolidation
  bias. The service-level guard on the durable `completed_by` marker yields
  the same product behaviour.
- **Fully root-only management** (the bootstrap account also manages
  `platform_observer`): rejected — appointed admins must handle day-to-day
  observer management.
- **Open delegation** (any `platform_admin` grants/revokes any other, root
  excepted): rejected — appointed admins must be able neither to eject each
  other nor to grow the admin population.
- **Status quo** (ops-only `fga` writes): rejected — the prod migration
  cleanup shows this is a real, recurring need.

Accepted limits:

- An operator with direct OpenFGA access can still delete the root tuple.
  Out of product scope — that access level is root-equivalent anyway.
- If the root account is lost (person leaves, Keycloak account deleted),
  the `platform_admin` population is frozen: nobody can grant or revoke
  admins through the product. Recovery is an ops-level OpenFGA tuple write —
  accepted by the developer as the price of the strict model.

## 5. Impact on contracts

- `CONTROL-PLANE-PRODUCT-CONTRACT.md`: dated entry for the three endpoints
  (written at implementation time). No database change of any kind.
- Generated client: `make update-control-plane-api` in the same change; the
  admin UI consumes the generated hooks only.
- `docs/swift/ux/COMPONENT-UX.md`: entry for the new PlatformRolesPage once
  implemented (doc checklist "UX component implemented").
- `REBAC.md`: once shipped, replace "or explicit admin action" with a pointer
  to the real endpoints and fold the durable what/why there — then trim this
  RFC per the 2026-08-01 RFC-vs-doc rule.

## 6. Open questions

None on the model (decided 2026-08-21). The list-endpoint response shape is
specified in §3.1.
