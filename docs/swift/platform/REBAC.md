# Relationship-Based Access Control (ReBAC)

Fred supports relationship-aware authorization so users can keep resources private, share them with teams, or publish them broadly.

> [!IMPORTANT]
> **Frequent deployment pitfall:**
> Keycloak app roles (`admin`/`editor`/`viewer`) no longer exist as of AUTHZ-05 review
> item 8a — Keycloak is identity-only. Team rights (`team_admin`/`team_editor`/
> `team_analyst`/`team_member`) and platform roles (`platform_admin`/`platform_observer`)
> are ReBAC relations stored in OpenFGA, never derived from Keycloak roles or groups.
> Team resource updates require team relations (`team_editor` or `team_admin`) and are
> not automatically granted by any platform role.
> In production, bootstrap team roles through the platform-admin-gated team-bootstrap endpoint (see below), not a Keycloak role.

> [!IMPORTANT]
> **AUTHZ-05 update (2026-07-09, two passes):** `team.owner` used to silently include
> `admin from organization` — any Keycloak `admin` was an implicit owner of every
> team. That was a live escalation bug; it has been removed (see
> [FRED-AUTHORIZATION-TARGET-MODEL-RFC §24.2](../rfc/FRED-AUTHORIZATION-TARGET-MODEL-RFC.md#242-escalation-fix-21--new-item-not-in-the-original-six)).
> A first attempt at a "deliberate exception" (platform_admin reaching
> `can_administer_owners`/`can_administer_managers`) was tried and **reverted the
> same day** — PR #1957 review found it was the same escalation through a
> different door, since OpenFGA cannot express "only if this team has no owner
> yet" (RFC §24.7). **`platform_admin` carries no team relation of any kind,
> full stop** — not even for team creation. Team creation and the first
> `team_admin` grant are instead a distinct, one-shot, platform-admin-gated
> **bootstrap action** (`POST /teams`, RFC §28), not an implicit relation.
> Team roles were also renamed in the second pass: `owner`→`team_admin`,
> `manager`→`team_editor`, plus a new `team_analyst` role — see RFC §26.
> The organization-level content bypass found in the first pass
> (`can_read_content`/`can_process_content` were organization-scoped, not
> team-scoped, across most of knowledge-flow-backend) is now fixed for every
> call site where team-scoping is mechanically meaningful — RFC §27.

> [!IMPORTANT]
> **AUTHZ-05 review item 8a (2026-07-10):** the legacy Keycloak `admin`/`editor`/
> `viewer` organization relations are removed from `schema.fga` entirely — Keycloak
> is now identity-only, with no role bridge of any kind. The five admin-tier
> capabilities they used to satisfy (`can_administer_users`, `can_manage_platform`,
> `can_run_benchmark`, `can_edit_agent_class_path`, `can_read_kpi_global`) are
> `platform_admin`-only now. The seven "any connected user" capabilities they used
> to satisfy (`can_read_content`, `can_process_content`, `can_create_agent`,
> `can_read_kpi`, `can_read_logs`, `can_read_metrics`, `can_read_opensearch`) never
> protected anything specific — they are removed outright, not replaced by another
> relation; the corresponding endpoints rely on authentication alone (see RFC Part 6
> §29-32).

> [!IMPORTANT]
> **AUTHZ-05 review item 9 (2026-07-10): teams are no longer Keycloak groups.**
> A team is now purely a `team_metadata` row (id, name) plus its OpenFGA relations.
> Keycloak manages user accounts (login, JWT, stable `sub`) and nothing about teams
> — no root group, no group membership, no group CRUD. `POST /teams` generates a
> fresh `uuid4().hex` id and writes the metadata row directly; membership reads go
> through `team_member` (already covering `team_admin`/`team_editor`/`team_analyst`
> via the schema's union relation) instead of a Keycloak group-member fetch. Three
> new platform-admin-gated, registry-only capabilities exist alongside
> `can_create_team` (RFC Part 6 §32): `can_list_all_teams` (`GET /teams/all`),
> `can_delete_team` (`DELETE /teams/{team_id}`), and `can_rescue_team_admin`
> (`POST /teams/{team_id}/rescue-admin`) — the last one writes a `team_admin` tuple
> **only if the team currently has zero `team_admin`**, the guard that keeps it from
> being the same escalation as the reverted `§24.7` attempt. Translating
> already-existing, already-live Keycloak-group-backed teams onto this model is a
> distinct, separately tracked operational concern (RFC §29) — out of scope for a
> fresh deployment with zero pre-existing teams.

## Business View In 90 Seconds

Use this mental model first:

1. Every authenticated user can use the platform (there is no separate "global role" gating basic use — see item 8a).
2. Each person also has a **team role** inside each team.
3. To create, edit, or delete team content (for example a library), the **team role** is what matters.
4. A `platform_admin` can still be blocked in a team if they are not team editor or team admin there — platform roles carry no team access.
5. Every team's first `team_admin` is granted through the platform-admin-gated bootstrap endpoint at team creation; there is no automatic assignment after that.

Concrete examples:

1. Alice is `platform_admin` but only team member in Thales: she can access the app, but cannot create a library in Thales.
2. Bob is team editor in Northbridge: he can create/update libraries in Northbridge.
3. Phil is team member in Swiftpost: he can consult shared content but cannot manage team content.
4. A newly created team always has at least one `team_admin`, set at creation time by the bootstrap endpoint — there is no path to a team with zero admins.

## Technical Summary In 90 Seconds

1. **Identity source**: Keycloak manages user accounts (login, JWT, stable `sub`) — nothing about teams or platform roles.
2. **Platform roles (ReBAC)**: `platform_admin` / `platform_observer` are relations in OpenFGA, stored tuples only, granted via config-seeded bootstrap or explicit admin action — never derived from Keycloak roles or groups.
3. **Team/resource rights (ReBAC)**: `team_admin` / `team_editor` / `team_analyst` / `team_member` are relations in OpenFGA and control team-scoped operations.
4. **Bridge object**: Fred uses one organization object (`organization:fred`) for global role context, without implicit team privilege escalation.
5. **Deployment rule**: a team's first `team_admin` comes from the bootstrap endpoint at team creation, not from Keycloak roles or post-install scripts guessing at ownership.

Enabling it allows to;

- Enforce private libraries by default and explicitly share with collaborators.
- Express more than role checks (e.g.,a user or group “owner”/“member”/“viewer” on a specific library).

Without ReBAC, all resources (like librairies and documents) are public (all users can view, edit, delete... them).

---

## Product authorization model

This section is the locked design authority for all team configuration work.
It states who can touch what at the product level. The technical enforcement
mechanism is described in the sections that follow.

### Team bootstrap — platform admin, one-shot only

Team creation is not a team relation at all — it is a distinct, one-shot,
platform-admin-gated action, `POST /teams { name, initial_team_admin_ids }`
(RFC §28). `platform_admin` does not become a team relation of any kind by
performing this action; it writes explicit `team_admin` tuples for exactly the
subjects named in the request. The endpoint 409s if the team already exists,
so it cannot be reused to change an existing team's admins — that path stays
gated on the team's own `team_admin`(s), never on `platform_admin`.

### Team admin — team `team_admin`

Responsible for team governance.

Can:

- assign and revoke `team_admin`, `team_editor`, `team_analyst`, `team_member`
  on their team (after the team's first `team_admin` was set at bootstrap)
- define and update `TeamPlatformPolicy` (quotas, allowed model profiles,
  allowed MCP servers, storage and ingestion limits)
- read any team configuration surface for audit purposes

Cannot:

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

Cannot:

- modify `TeamPlatformPolicy`
- create teams or assign team roles

### Team analyst — team `team_analyst`

Responsible for evaluating agents using controlled, team-scoped evaluation
data.

Can:

- create and run evaluation campaigns; manage evaluation corpora
- access the limited conversation slices required for evaluation datasets

Cannot:

- manage all corpus resources, change governance settings, or administer team
  membership

### Team member — team `team_member`

Can:

- use team-managed agents
- use prompts visible in their team context
- manage their own personal prompts

Cannot:

- configure any team-wide setting, policy, or shared resource

### Deployment admin

Out of scope for day-to-day product UI.

**Design rule:** no product contract may rely on implicit global-admin
escalation for team-scoped writes. A `platform_admin` who is not an explicit
team relation holder is blocked for team-scoped writes. Every team-scoped
write must pass explicit team-scoped authorization.

### Hard cross-write rule

The `team_admin` and `team_editor` roles are **orthogonal on the business
surface**, not hierarchical.

- A `team_admin` has full authority over governance and zero authority over
  agents, prompts, and routing policy.
- A `team_editor` has full authority over agents, prompts, routing policy, and
  corpus content, and zero authority over platform guardrails.
- Neither role grants implicit access to the other's surfaces.

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

- The `knowledge-flow` and `agentic`client needs `realm-management: query-users, query-groups, view-users` and `account: view-groups` to be able to list users and groups from Keycloak
- `knowledge-flow` needs in addition `realm-management: manage-users` client roles to be able to add/remove users from groups
- Keycloak must send the `groups` claim in access tokens (see `groups-scope` client scope in [KEYCLOAK.md](./KEYCLOAK.md)).

## Organization concept (`organization:fred`)

Fred uses a singleton organization node in ReBAC:

- Object id: `organization:fred`
- Purpose: hold platform role context (`platform_admin`/`platform_observer`, stored OpenFGA tuples only) without automatically turning these roles into team `team_admin`/`team_editor` rights.

How it works:

1. Platform roles are explicit stored tuples on `organization:fred`, granted via config-seeded bootstrap (`platform_admin_subjects`) or explicit admin action — never derived from the Keycloak token (AUTHZ-05 review item 8a removed the last Keycloak-role-derived contextual relation).
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
    platform_admin_subjects: [] # AUTHZ-05: Keycloak `sub` values granted `platform_admin` at startup, idempotently
    platform_observer_subjects: [] # AUTHZ-05: Keycloak `sub` values granted `platform_observer` at startup
```
