# Relationship-Based Access Control (ReBAC)

Fred supports relationship-aware authorization so users can keep resources private, share them with teams, or publish them broadly.

> [!IMPORTANT]
> **Frequent deployment pitfall:**
> Keycloak app roles (`admin`/`editor`/`viewer`) are global RBAC roles.
> Team rights (`owner`/`manager`/`member`) are ReBAC relations stored in OpenFGA.
> Team resource updates require team relations (`manager` or `owner`) and are not automatically granted by app role alone.
> In production, bootstrap team roles through an automated post-install step.

## Business View In 90 Seconds

Use this mental model first:

1. Each person has a **global role** that defines what they can do in the application overall.
2. Each person also has a **team role** inside each team.
3. To create, edit, or delete team content (for example a library), the **team role** is what matters.
4. A global admin can still be blocked in a team if they are not team manager or team owner there.
5. After installation, team managers/owners must be assigned automatically by deployment scripts.

Concrete examples:

1. Alice is global admin but only team member in Thales: she can access the app, but cannot create a library in Thales.
2. Bob is global editor and team manager in Northbridge: he can create/update libraries in Northbridge.
3. Phil is global viewer and team member in Swiftpost: he can consult shared content but cannot manage team content.
4. Fresh installation with no team manager/owner assigned: users can log in, but team management actions fail.

## Technical Summary In 90 Seconds

1. **Identity source**: Keycloak manages users and teams (teams are Keycloak groups).
2. **Global app roles (RBAC)**: `admin` / `editor` / `viewer` define application-wide capabilities.
3. **Team/resource rights (ReBAC)**: `owner` / `manager` / `member` are relations in OpenFGA and control team-scoped operations.
4. **Bridge object**: Fred uses one organization object (`organization:fred`) for global role context, without implicit team privilege escalation.
5. **Deployment rule**: post-install automation must create the required team relations; do not wait for manual UI actions.

Enabling it allows to;
- Enforce private libraries by default and explicitly share with collaborators.
- Express more than role checks (e.g.,a user or group “owner”/“member”/“viewer” on a specific library).

Without ReBAC, all resources (like librairies and documents) are public (all users can view, edit, delete... them).

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
- Purpose: hold global application role context (`admin`/`editor`/`viewer`) without automatically turning these roles into team owner/manager rights.

How it works:

1. At authorization time, the backend derives contextual relations from the user token (for example: user has `admin` role on organization).
2. Team checks rely on persistent tuples linking teams to the organization:
   - `organization:fred#organization@team:<team_id>`
3. Team permissions still require explicit team relations (`owner`/`manager`/`member`) for the target team.

Important consequence:

- A global `admin` user can still be denied team operations when they are not explicit `owner` or `manager` of that team.
- Deployment must bootstrap team `owner`/`manager` relations during post-install.

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
    enabled: true                     # Set false to bypass ReBAC (warning: all private resources will become public)
    type: openfga
    api_url: "http://localhost:9080"  # OpenFGA HTTP endpoint
    store_name: "fred"                # OpenFGA store name. Reuse the same store across services
    create_store_if_needed: true      # Automates store bootstrap (disable if pre-provisioned)
    sync_schema_on_init: true         # Pushes the default Fred authorization model
    authorization_model_id: null      # Authorization model id to use in case `sync_schema_on_init: false`
    token_env_var: "OPENFGA_API_TOKEN" # Env var holding the bearer token
    timeout_millisec: 2000            # Optional request timeout
    headers:
      # Optional static headers sent to OpenFGA
      X-Custom-Header: "value"
```
