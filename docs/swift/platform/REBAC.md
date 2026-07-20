# Relationship-Based Access Control (ReBAC)

Fred supports relationship-aware authorization so users can keep resources private, share them with teams, or publish them broadly.

> Frontend counterpart: [`FRONTEND-AUTHZ-PATTERN.md`](./FRONTEND-AUTHZ-PATTERN.md) —
> how the two hooks (`useUserCapabilities`, `useTeamCapabilities`) consume the
> model described below, and how that layer is tested.

> [!IMPORTANT]
> **Keycloak authenticates, Fred/OpenFGA authorizes — no exceptions.** Keycloak
> app roles (`admin`/`editor`/`viewer`) do not exist. Keycloak manages only user
> accounts (login, JWT, stable `sub`) — nothing about teams or platform roles.
> Every platform role (`platform_admin`/`platform_observer`) and every team role
> (`team_admin`/`team_editor`/`team_analyst`/`team_member`) is a stored OpenFGA
> relation, granted through the root bootstrap endpoint (a one-time,
> secret-gated `POST /bootstrap/platform-admin` — AUTHZ-07, RFC Part 8) or an
> explicit in-product action — never derived from a Keycloak role, group, or
> claim. A `platform_admin`
> carries no team relation of any kind, ever, for any purpose — not even to
> create a team's first admin, which goes through the one-shot bootstrap
> endpoint below, not an implicit relation.

## Business View In 90 Seconds

Use this mental model first:

1. Every authenticated user can use the platform — there is no separate "global role" gating basic use.
2. Each person also has zero or more **team roles**, per team — a person may hold several roles on the same team at once (e.g. a small team's sole admin who is also its editor and evaluator).
3. To create, edit, or delete team content (for example a library), the **team role** is what matters — a platform role never substitutes for it.
4. A `platform_admin` can still be blocked in a team if they hold no team role there.
5. Every team's first `team_admin` is granted through the platform-admin-gated bootstrap endpoint at team creation; there is no automatic assignment after that, and no path to a team with zero admins.

Concrete examples:

1. Alice is `platform_admin` but only a team member in Thales: she can access the app, but cannot create a library in Thales.
2. Bob is team editor in Northbridge: he can create/update libraries in Northbridge.
3. Phil is team member in Swiftpost: he can consult shared content but cannot manage team content.
4. Sophia is both `team_admin` and `team_editor` of Fredlab (a small team, one person wearing both hats): she governs membership **and** edits content there — each role was granted to her independently.

## Technical Summary In 90 Seconds

1. **Identity source**: Keycloak manages user accounts (login, JWT, stable `sub`) — nothing about teams or platform roles.
2. **Platform roles (ReBAC)**: `platform_admin` / `platform_observer` are relations on `organization:fred`, stored tuples only, granted via the root bootstrap endpoint (`POST /bootstrap/platform-admin`, AUTHZ-07) or explicit admin action.
3. **Team roles (ReBAC)**: `team_admin` / `team_editor` / `team_analyst` / `team_member` are relations on each `team:<id>`. A person may hold more than one simultaneously — each is granted/revoked as its own independent action, never a bulk replace.
4. **Team registry**: a team is a `team_metadata` row (id, name) plus its OpenFGA relations — nothing about a team lives in Keycloak.
5. **Bridge object**: Fred uses one organization object (`organization:fred`) for platform-wide context, without implicit team privilege escalation.
6. **Deployment rule**: a team's first `team_admin` comes from the bootstrap endpoint at team creation, never from Keycloak roles or a post-install script guessing at ownership.

Enabling it allows to;

- Enforce private libraries by default and explicitly share with collaborators.
- Express more than role checks (e.g., a user or group "owner"/"member"/"viewer" on a specific library).

Without ReBAC, all resources (like libraries and documents) are public (all users can view, edit, delete... them).

---

## Product authorization model

This section is the locked design authority for all team configuration work.
It states who can touch what at the product level. The technical enforcement
mechanism is described in the sections that follow.

### Team bootstrap — platform admin, one-shot only

Team creation is not a team relation at all — it is a distinct, one-shot,
platform-admin-gated action, `POST /teams { name, initial_team_admin_ids }`.
`platform_admin` does not become a team relation of any kind by performing this
action; it writes explicit `team_admin` tuples for exactly the subjects named
in the request. The endpoint 409s if the team already exists, so it cannot be
reused to change an existing team's admins — that path stays gated on the
team's own `team_admin`(s), never on `platform_admin`.

### Team roles are cumulative, not exclusive

A person may hold `team_admin`, `team_editor`, and `team_analyst` on the same
team at the same time — common on small teams where one person governs, edits
content, and evaluates. Nothing in the OpenFGA schema enforces exclusivity;
each role is an independent stored relation. Each grant and each revoke is its
own explicit, individually permission-checked action (`POST
/teams/{team_id}/members/{user_id}/roles`, `DELETE
/teams/{team_id}/members/{user_id}/roles/{relation}`) — never a bulk "replace
the role set" call. Revoking a member's only remaining role is refused (use
`DELETE /teams/{team_id}/members/{user_id}` to remove them entirely instead).

### Team admin — team `team_admin`

Responsible for team governance.

Can:

- assign and revoke `team_admin`, `team_editor`, `team_analyst`, `team_member`
  on their team (after the team's first `team_admin` was set at bootstrap)
- define and update `TeamPlatformPolicy` (quotas, allowed model profiles,
  allowed MCP servers, storage and ingestion limits)
- read any team configuration surface for audit purposes

Cannot (unless also separately granted `team_editor`/`team_analyst` — see
above):

- create, edit, or delete agent instances
- create, edit, or delete shared or personal prompts
- set or update `TeamRoutingPolicy`

### Team editor — team `team_editor`

Responsible for what the team does with the platform within the bounds set by
the team admin.

Can:

- configure `TeamRoutingPolicy`
- manage shared team prompts (create, update, score, promote)
- manage team agent instances (enroll, tune, archive)
- add, update, move, and remove team corpus resources
- read `TeamPlatformPolicy` as a constraint — not editable

Cannot (unless also separately granted `team_admin`):

- modify `TeamPlatformPolicy`
- create teams or assign team roles

### Team analyst — team `team_analyst`

Responsible for evaluating agents using controlled, team-scoped evaluation
data.

Can:

- create and run evaluation campaigns; manage evaluation corpora
- access the limited conversation slices required for evaluation datasets

Cannot (unless also separately granted `team_admin`/`team_editor`):

- manage all corpus resources, change governance settings, or administer team
  membership

### Team member — team `team_member`

The implicit baseline: automatic for anyone holding any role above, or
granted directly to someone with no elevated role.

Can:

- use team-managed agents
- use prompts visible in their team context
- manage their own personal prompts

Cannot:

- configure any team-wide setting, policy, or shared resource

### Personal teams — self-provisioned, never admin-writable (AUTHZ-08)

A personal team (`personal-<uid>`) is a real ReBAC team object, but it does
**not** follow the "granted through bootstrap or explicit admin action" rule
above — that rule is about *collaborative* teams, where ownership must be
assigned because it isn't otherwise knowable. A personal team's owner is
knowable by construction (the uid is embedded in the team id), so it is
provisioned automatically instead:

- `RebacEngine.check_user_permission_or_raise`/`has_user_permission`
  (`fred-core`, shared by every backend) self-heal exactly one tuple —
  `user:<uid> team_editor team:personal-<uid>` — the first time its own owner
  touches a personal-team permission check. `team_editor` reproduces
  control-plane's synthetic `build_personal_team` DTO permission set
  (`can_read`, `can_update_resources`, `can_update_agents`) exactly.
- `RebacEngine.add_relation` — the one audited chokepoint every relation write
  funnels through, collaborative or personal — refuses any tuple naming a
  personal team except that owner self-grant and the structural
  `organization -> team` edge every team gets. No admin API, import/export
  path, or future caller can write a tuple granting anyone else access to
  someone else's personal space; this invariant is what makes writing a real,
  persisted tuple safe for a resource type that otherwise has no assignable
  owner.

Never add a personal team to `initial_team_admin_ids`, a member-role grant
endpoint, or any bulk relation-writing tool — `add_relation` rejects it, by
design, regardless of caller.

### Team registry governance — platform admin, existence only

Three narrow, `platform_admin`-only capabilities govern the team *registry*
(which teams exist) — none of them grant access to a team's data:

- **`can_list_all_teams`** → `GET /teams/all`: every team in the registry,
  regardless of the caller's own membership.
- **`can_delete_team`** → `DELETE /teams/{team_id}`: deletes the registry row
  and every relation referencing that team.
- **`can_rescue_team_admin`** → `POST /teams/{team_id}/rescue-admin`: grants
  `team_admin` to a named user, **only if the team currently has zero
  `team_admin`** — mechanically inert against any team with an active admin.
  Never generalize this into "platform_admin can reassign any team's admin at
  any time" — that is a live escalation, not a rescue.

### Platform observability — `can_observe_platform`

The one relation for cross-user / platform-wide KPI observation — granted to
`platform_observer` (which unions in `platform_admin`). Gates both the
standalone KPI dashboard and the control-plane Analytics presets: today
`platform_admin` and `platform_observer` see the same platform-wide recap.
When the Analytics surface grows admin-only technical panels, gate those
specific widgets on a new, narrower capability — don't split platform-wide
observation into two relations again.

### Deployment admin

Out of scope for day-to-day product UI.

**Design rule:** no product contract may rely on implicit global-admin
escalation for team-scoped writes. A `platform_admin` who is not an explicit
team relation holder is blocked for team-scoped writes. Every team-scoped
write must pass explicit team-scoped authorization.

### Hard cross-write rule

`team_admin` and `team_editor` grant **orthogonal capabilities**, not
hierarchical ones — holding one does not imply the other's authority.

- The `team_admin` role's authority covers governance only: zero authority
  over agents, prompts, and routing policy unless `team_editor` is also
  separately held.
- The `team_editor` role's authority covers agents, prompts, routing policy,
  and corpus content only: zero authority over platform guardrails unless
  `team_admin` is also separately held.
- A person may hold both (see "Team roles are cumulative" above) — but each
  role's authority still only reaches its own surface. Holding both is two
  separate grants, not a merged super-role.

There is no exception for team creation or first-admin assignment: that is the
bootstrap endpoint above, not a relation any role holds.

This rule must be enforced at the API layer. It is not sufficient to rely on
UI-level restrictions.

---

## Engine choice

Fred uses **OpenFGA** as the ReBAC engine (compatible with the Zanzibar model).

- Deployment guidance for OpenFGA: https://openfga.dev/docs/getting-started/setup-openfga/overview

## Prerequisites

- [Deploy OpenFGA](https://openfga.dev/docs/getting-started/setup-openfga/overview) (localy, with Docker, on Kubernetes...) and provide an API token to the ReBAC engine (see `token_env_var` below).

Keycloak options (see [KEYCLOAK.md](./KEYCLOAK.md) for more details):

- The `knowledge-flow` and `agentic` client needs `realm-management: query-users, view-users` to list users from Keycloak (directory/identity lookups only — team membership and roles are never derived from Keycloak).

**No group-derived authorization.** AUTHZ-05 removed every Keycloak-groups
consumer: the periodic Keycloak→ReBAC group reconciliation task, the
per-request JWT `groups`-claim-derived `team_member` contextual relation
(`groups_list_to_relations`/`_user_contextual_relations`, RFC §18/24.1, review
item 8b), the `groups` field on `KeycloakUser`, and the `groups` KPI
dimension. `decode_jwt` no longer reads a `groups` claim at all — a JWT that
still carries one is accepted (no unknown-claim error) but the claim is
silently ignored end to end. No JWT `groups` claim, no Keycloak group
membership, and no `realm-management: query-groups`/`view-groups`/
`manage-users`-for-groups/`groups-scope` client scope are required or read.
Every team membership, at every scope, must be a persisted OpenFGA tuple.

## Organization concept (`organization:fred`)

Fred uses a singleton organization node in ReBAC:

- Object id: `organization:fred`
- Purpose: hold platform role context (`platform_admin`/`platform_observer`, stored OpenFGA tuples only) without automatically turning these roles into team `team_admin`/`team_editor` rights.

How it works:

1. Platform roles are explicit stored tuples on `organization:fred`, granted via the root bootstrap endpoint (`POST /bootstrap/platform-admin`, one-time and secret-gated — AUTHZ-07) or explicit admin action — never derived from the Keycloak token, and never declared as a `sub` in deployment config.
2. Team checks rely on persistent tuples linking teams to the organization:
   - `organization:fred#organization@team:<team_id>`
3. Team permissions still require explicit team relations (`team_admin`/`team_editor`/`team_analyst`/`team_member`) for the target team.

Important consequence:

- A `platform_admin` user can still be denied team operations when they are not an explicit team relation holder for that team.
- A team's first `team_admin` is set once, at team creation, by the bootstrap endpoint — not by post-install scripts guessing at ownership.

## Configuration

Here is the minimal configuration to enable ReBAC (Agentic/Knowledge Flow):

```yaml
security:
  # ...
  rebac:
    type: openfga
    api_url: "http://localhost:9080"
```

And set `OPENFGA_API_TOKEN` in the environment.

By default the backend will create the store (if missing) and push the Fred authorization model at startup. You can turn that off (with `create_store_if_needed` and `sync_schema_on_init`) if you manage OpenFGA yourself. In that case, we recommend you to pass a a static authorization model id with `authorization_model_id`.

### Full commented configuration

```yaml
security:
  # ...
  rebac:
    enabled: true # Set false to bypass ReBAC (warning: all private resources will become public)
    type: openfga
    api_url: "http://localhost:9080" # OpenFGA HTTP endpoint
    store_name: "fred" # OpenFGA store name. Reuse the same store across services
    create_store_if_needed: true # Automates store bootstrap (disable if pre-provisioned)
    sync_schema_on_init: true # Pushes the default Fred authorization model
    authorization_model_id: null # Authorization model id to use in case `sync_schema_on_init: false`
    token_env_var: "OPENFGA_API_TOKEN" # Env var holding the bearer token
    timeout_millisec: 2000 # Optional request timeout
    headers:
      # Optional static headers sent to OpenFGA
      X-Custom-Header: "value"
```

> **No config-seeded platform roles.** `platform_admin_subjects`/`platform_observer_subjects`
> (a Keycloak `sub` list granted platform roles at OpenFGA-engine startup) existed under
> AUTHZ-05 §24.3 and was removed by AUTHZ-07 (RFC Part 8 §40-41): it was a second,
> parallel authority alongside root bootstrap + declarative import, and an opaque
> per-realm UUID in versioned/secret config is fragile across realm re-imports. The first
> `platform_admin` is granted exclusively by `POST /control-plane/v1/bootstrap/platform-admin`
> (self-promotion only, see §3.1.2 of `CONTROL-PLANE-PRODUCT-CONTRACT.md`); every other
> platform or team role is granted exclusively by the declarative platform import
> (`PLATFORM-IMPORT-RFC.md` §10). No field in `security.rebac` configures a platform role
> anymore.
