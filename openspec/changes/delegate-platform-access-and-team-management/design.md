## Context

See `proposal.md`. The OpenFGA model currently derives all platform access administration from `can_manage_platform`, which also gates unrelated global actions. `team_manager` has `can_create_team` and `can_list_all_teams` only. The registry edit request combines name, description and admin changes. The admission team's `allowed` and `free` flags share one update body, while Free-link routes share the platform access admin dependency. These combinations need separate server checks before delegation is safe.

## Goals / Non-Goals

**Goals:**

- Make every action in Platform Access usable by a delegated platform access manager, including whitelist, filtering, rules, T0 and Free management.
- Give team managers name/description and Free controls without allowing admin nomination or changes to independent team authorization.
- Preserve current link enrollment, audit, lockout and `platform_admin` behavior.

**Non-Goals:**

- Grant team managers team content or member-administration permissions.
- Change the Free admission model or the existing team invite link model.
- Add a data migration or a new table.

## Decisions

### 1. Add computed organization permissions with explicit role membership

Add `platform_access_manager: [user] or platform_admin`, `can_manage_platform_access: platform_access_manager`, and `can_manage_team_free: platform_access_manager or team_manager` to `schema.fga`. Add `can_edit_team_info: team_manager`, leaving `can_edit_team_registry`, team deletion and admin rescue on `platform_admin`. Include `platform_access_manager` in `can_list_all_teams` so its holder can reach the existing Admin Teams Free controls; that read exposes registry metadata and admins' identity summaries, as documented in `REBAC.md`, but grants no registry mutation. As with existing delegated roles, the `platform_admin` union preserves its access. Wire the new role through the role relation enum, role assignment, bootstrap summary, frontend capability list and generated types. This keeps the permissions in the authorization model rather than inferring them from frontend state or a Keycloak role. Reusing `can_manage_platform` would grant platform reset, import/export and unrelated global powers.

### 2. Gate full Platform Access with the narrow permission

Change the platform access admin dependency to `can_manage_platform_access`. Use that same current permission in the admission bypass and activation preview/actor-safeguard checks, so a platform access manager can reach the page while filtering is active and loses that source immediately when the role is revoked. Keep suspension, terms and resource checks. The existing Platform Access routes and request/response shapes remain intact for callers with the full permission. Free-link routes use the separate `can_manage_team_free` check and retain their own-human credential requirement for creation and token recovery. They still restrict reads and writes to Free links of the requested team.

### 3. Give team managers a Free-only write path

Keep the existing `PATCH /admin/platform/access/teams/{team_id}` guarded by `can_manage_platform_access`, because its body changes both `allowed` and `free`. Add a bounded Free-only read and update under the same route family for the Admin Teams page. The Free update changes only `platform_access_free` within the existing mutation and actor-safeguard transaction, leaving `platform_access_allowed` untouched. The read returns only team ids and Free state; it does not expose policy, individual exceptions or team authorization. Both routes require `can_manage_team_free`. The Admin Teams page uses this read and write for its Free toggle, while the Platform Access whitelist keeps its existing full-authority endpoints. Directly letting team managers send the combined `allowed`/`free` body would allow escalation or depend on a fragile comparison of untrusted payload and stored state.

### 4. Check registry edit fields before any write

The existing registry edit route accepts both details and admin changes. Require `can_edit_team_info` for every request and require `can_edit_team_registry` as well whenever `add_admin_ids` or `remove_admin_ids` is nonempty, before metadata or relations are written. Keep current validation, locking, rename handling and audit. In the shared UI dialog, show admin selection during creation and to platform admins during editing; show only name and description when a team manager edits. A new details endpoint would duplicate validation and audit logic without improving the boundary.

### 5. Expose only the permitted UI surfaces

Add `canManagePlatformAccess` to the bootstrap-derived frontend capabilities and route/navigation gate. Let that role reach the Admin Teams page for Free controls, with Create and Edit hidden unless it also holds `team_manager`. Make the Free toggle and link manager available to both `team_manager` and `platform_access_manager`; keep registry editing behind its separate role. The server remains authoritative. Update the role selector and French/English labels, regenerate the control-plane client from the OpenAPI contract, and update the endpoint matrix and compact security/product docs.

## Risks / Trade-offs

- **Team managers can now cause platform admission through Free links:** The Free-only permission is intentionally broad across collaborative teams, matching their registry scope. Explicit role assignment, security audit, and current Free-link protections provide accountability.
- **An existing combined endpoint could accidentally expose `allowed`:** Keep its full permission and add focused denial tests for team managers, including crafted mixed payloads.
- **Admission bypass depends on live OpenFGA state:** Use the higher-consistency check already used for platform admins and retain the existing 503 behavior when authority is unavailable.
- **Generated clients and deployed authorization models can drift:** Deploy the updated OpenFGA model before backend/frontend use the new relations; verify schema transformation, generated types and focused role isolation tests. Rollback the application before reverting the model if needed.

## Migration Plan

No SQL migration. Update the OpenFGA model first, then deploy the control plane and frontend. Existing tuples and Free links remain valid; no role is assigned automatically. Revoking a delegated role withdraws its management and admission authority on subsequent requests. A rollback keeps the added OpenFGA relations inert until the older application is restored.
