# Relationship-Based Access Control (ReBAC)

Fred supports relationship-aware authorization so users can keep resources private, share them with teams, or publish them broadly.

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
