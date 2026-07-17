# Frontend Authorization Pattern

The frontend counterpart to [`REBAC.md`](./REBAC.md). Read this before adding
any UI element, route, or button whose visibility depends on who the user is.

> [!IMPORTANT]
> **AUTHZ-05 review item 11 (2026-07-11):** the frontend used to have three
> competing ways to answer "can this user do X" — one correct and centralized
> (org tier), one correct but duplicated across ~9 components (team tier), and
> one entirely dead (`usePermissions()`, reading a Keycloak-role-derived list
> that AUTHZ-05 emptied for every user platform-wide). The dead one silently
> disabled 6 routes and 3 in-page controls for **everyone, including
> platform_admin**, until this pass. The resulting frozen-contract correction
> is recorded in `CONTROL-PLANE-PRODUCT-CONTRACT.md` §14.

## The two-tier model

Exactly two hooks. Both are pure derivations of data control-plane already
sends on every bootstrap/team fetch — neither one calls a new endpoint.

| Tier                                    | Hook                       | Reads                                                  | Backing data                                                                       |
| ---------------------------------------- | -------------------------- | ------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| Org-level (singleton, `organization:fred`) | `useUserCapabilities()`    | `canAdmin`, `canObservePlatform`                         | `FrontendBootstrap.permissions.{is_platform_admin,is_platform_observer}` (OpenFGA)  |
| Team-level (per team_id)                 | `useTeamCapabilities(team)` | `canRead`, `canUpdateInfo`, `canUpdateResources`, `canUpdateAgents`, `canReadMembers`, `canAdministerMembers`, `canAdministerEditors`, `canAdministerAnalysts`, `canAdministerAdmins`, `canReadConversations`, `canUseTeamAgents`, `canRunEvaluations`, `canManageEvaluationCorpus`, `canReadConversationsForEvaluation` | `TeamWithPermissions.permissions` (OpenFGA, per `teams/service.py::_get_team_permissions_for_user`) |

**Which one do I use?** If the answer to "can Alice do this" would ever
change depending on *which team* she's looking at, it's team-level. If the
answer is the same everywhere in the app for a given user, it's org-level.
When in doubt: everything under `/team/:teamId/...` is almost always
team-level; `/admin/*` and platform-wide dashboards are org-level.

`useTeamCapabilities` takes the `TeamWithPermissions` object you already have
in scope (from `useGetTeamQuery`, `useSelectedTeam`, or a prop) — it does not
fetch anything itself. There is no team-scoped route guard today: every
`/team/:teamId/...` route renders unconditionally, and team-level gating
happens *inside* the page (hide/disable a button, not redirect the route).

## Route guards

`src/components/Protected.tsx` is the one guard component, used only for the
org tier:

```tsx
<Protected requires="admin">      {/* canAdmin only */}
<Protected requires="observer">   {/* canAdmin OR canObservePlatform */}
```

It replaces three former components (`AdminProtectedRoute`,
`KpiObserverProtectedRoute`, the `resource`/`action` `ProtectedRoute`). Add a
team-scoped variant only when a route genuinely needs one — none does today.

**One documented asymmetry:** the 6 `/monitoring/*` dev/ops routes
(`runtime`, `data`, `logs`, `rebac-backfill`, `processors`,
`processors/runs/:id`) are `requires="admin"` on the frontend even though
AUTHZ-05 review item 8a dropped backend enforcement on several of the APIs
behind them to "authenticated only". This is deliberate: they are ops/dev
tooling no normal team role has a reason to open, and gating them on
`canAdmin` avoids exposing raw system internals to every authenticated user
by default. If a non-admin ever needs one of these pages, that's a product
decision to make explicitly, not a gate to quietly loosen.

## How to add a new capability

1. Backend: add the relation/permission to `schema.fga` and `TeamPermission`
   (team-level) or `PermissionSummary` (org-level, rare — prefer team-level).
2. `cd apps/frontend && make update-control-plane-api` to regenerate
   `controlPlaneOpenApi.ts`.
3. Add one line to `PERMISSION_TO_FLAG` in
   `src/rework/core/hooks/teamCapabilities.ts` (team-level) or wire the new
   boolean into `useUserCapabilities()` (org-level).

Step 3 is not optional in practice: `PERMISSION_TO_FLAG` is typed as
`Record<TeamPermission, keyof TeamCapabilities>`, so skipping it is a
**TypeScript compile error**, not a gap someone finds during a manual audit.
That's the whole point of this pattern — the compiler is the enforcement
mechanism for completeness, not a checklist.

## Banned patterns

Never write these — they are exactly how the item-11 incident happened:

- `KeyCloakService.GetUserRoles()` / any raw Keycloak role string check, for
  anything except `canDebug` (a developer affordance, not an authorization
  gate — see `useUserCapabilities.ts`).
- A new `.includes("can_...")` string literal outside
  `teamCapabilities.ts`. If you're writing one, you're duplicating logic that
  belongs in `useTeamCapabilities` instead.
- A new `resource`/`action` string-pair check (the pattern `usePermissions()`
  used). There is no live backend mechanism behind that shape anymore.

## The testing pyramid for this pattern

One line per layer — this is "is permission-gating tested" as a single page
to check, instead of grepping the repo:

| Layer                              | Proves                                                          | File                                                                                                                     |
| ----------------------------------- | ----------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Pure mapping logic                 | Every `TeamPermission` turns on exactly its own flag, nothing else | `apps/frontend/src/rework/core/hooks/teamCapabilities.test.ts`                                                          |
| Guard decision logic               | `admin`/`observer` requirement resolves correctly                 | `apps/frontend/src/components/Protected.test.ts`                                                                        |
| Backend derivation (unit)          | `is_platform_admin`/`is_platform_observer` come from OpenFGA, not Keycloak | `apps/control-plane-backend/tests/test_main.py::test_frontend_bootstrap_permission_summary_derives_platform_admin_from_rebac` |
| Live, self-service, in-browser      | Isolation (registry/users/foreign-team access match the account's own flags) **and** a real team-scoped write (create+delete a prompt) match the account's own `can_update_resources` — for the running admin or any other account (`/admin/self-test`, "Test another profile") | `apps/frontend/src/rework/features/pipeline/scenarios/authzProbeScenario.ts` + `useAuthzProbeRun.ts` (deps), unit-tested in `authzProbeScenario.test.ts` |
| Live, black-box, real running stack | The whole chain end-to-end, real JWT + real OpenFGA               | `validation/scenarios/test_platform_admin_capabilities.py`, `test_team_registry_authz.py`, `test_prompt_authz.py` |
| Manual / visual                    | The UI actually hides/shows what the data says it should          | The AUTHZ-05 campaign checklist artifact                                                                                |

**Known gap, not yet closed:** there is no component-render test harness in
this repo (`@testing-library/react` / jsdom are not installed) — `Protected`
and `useTeamCapabilities` are tested at the logic layer only, not by actually
rendering a route and asserting a redirect. Adding that harness is a real,
separate infrastructure decision (affects every future frontend test, not
just this feature) — raise it explicitly rather than adding it as a side
effect of an unrelated change.
