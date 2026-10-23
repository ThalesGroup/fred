## Context

See `proposal.md`. The OpenFGA model currently derives all platform access administration from `can_manage_platform`, which also gates unrelated global actions. `team_manager` has `can_create_team` and `can_list_all_teams` only. Platform Access already owns both team admission flags and Free-link routes, so one narrow role can cover that complete surface.

## Goals / Non-Goals

**Goals:**

- Make every action in Platform Access usable by a delegated platform access manager, including whitelist, filtering, rules, T0 and Free management.
- Keep team managers' existing create and list permissions unchanged.
- Preserve current link enrollment, audit, lockout and `platform_admin` behavior.

**Non-Goals:**

- Grant team managers team content or member-administration permissions.
- Change the Free admission model or the existing team invite link model.
- Add a data migration or a new table.

## Decisions

### 1. Add computed organization permissions with explicit role membership

Add `platform_access_manager: [user] or platform_admin` and `can_manage_platform_access: platform_access_manager` to `schema.fga`. Leave `team_manager` and the admin-only team registry permissions unchanged. Include `platform_access_manager` in `can_list_all_teams` so its holder can reach the existing Admin Teams Free controls; that read exposes registry metadata and admins' identity summaries, as documented in `REBAC.md`, but grants no registry mutation. As with existing delegated roles, the `platform_admin` union preserves its access. Wire the new role through the role relation enum, role assignment, bootstrap summary, frontend capability list and generated types. This keeps the permissions in the authorization model rather than inferring them from frontend state or a Keycloak role. Reusing `can_manage_platform` would grant platform reset, import/export and unrelated global powers.

### 2. Gate full Platform Access with the narrow permission

Change the platform access admin dependency, including Free-link routes, to `can_manage_platform_access`. Use that same current permission in the admission bypass and activation preview/actor-safeguard checks, so a platform access manager can reach the page while filtering is active and loses that source immediately when the role is revoked. Keep suspension, terms and resource checks. Existing Platform Access routes and request/response shapes remain intact; Free-link creation and token recovery retain their own-human credential requirement and restrict reads and writes to Free links of the requested team.

### 3. Keep Free enrollment inside Platform Access

Keep the existing `GET /admin/platform/access/teams` and `PATCH /admin/platform/access/teams/{team_id}` under `can_manage_platform_access`. The update body changes both `allowed` and `free`, so callers who can toggle Free must hold the complete platform access role. Keep the existing link routes and actor-safeguard transaction. No Free-only API or second permission is needed. Giving `team_manager` these routes would let a team-registry role change platform admission.

### 4. Expose only the permitted UI surfaces

Add `canManagePlatformAccess` to the bootstrap-derived frontend capabilities and route/navigation gate. Let that role reach the Admin Teams page for Free controls. Keep Create available to `team_manager` and Edit limited to `platform_admin`; hide Free controls from a caller with only `team_manager`. The server remains authoritative. Update the role selector and French/English labels, regenerate the control-plane client from the OpenAPI contract, and update the endpoint matrix and compact security/product docs.

## Risks / Trade-offs

- **Platform access managers can cause admission through Free links:** This is part of the role's explicit scope. Existing audit, own-human token checks and Free-link protections provide accountability.
- **The Admin Teams page combines registry and Free controls:** Gate each control independently in the UI and keep the server's full platform access permission on the combined `allowed`/`free` endpoint. Add focused denial tests for team managers, including crafted requests.
- **Admission bypass depends on live OpenFGA state:** Use the higher-consistency check already used for platform admins and retain the existing 503 behavior when authority is unavailable.
- **Generated clients and deployed authorization models can drift:** Deploy the updated OpenFGA model before backend/frontend use the new relations; verify schema transformation, generated types and focused role isolation tests. Rollback the application before reverting the model if needed.

## Migration Plan

No SQL migration. Update the OpenFGA model first, then deploy the control plane and frontend. Existing tuples and Free links remain valid; no role is assigned automatically. Revoking a delegated role withdraws its management and admission authority on subsequent requests. A rollback keeps the added OpenFGA relations inert until the older application is restored.
