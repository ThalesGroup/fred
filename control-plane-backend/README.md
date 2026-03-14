# Control Plane Backend

Small control-plane service for team lifecycle and policy-driven conversation operations.

## Configuration Contract (All Fred Backends)

Control Plane follows the same startup configuration contract as Agentic and Knowledge Flow.

Read: [`docs/CONFIGURATION_AND_POLICY_CONVENTIONS.md`](../docs/CONFIGURATION_AND_POLICY_CONVENTIONS.md)

Key point: always use `ENV_FILE` + `CONFIG_FILE` (same names in every backend).

## What is inside

- FastAPI app for health/readiness and policy resolution endpoints
- FastAPI endpoint to remove a team member and enqueue conversation purge
- YAML policy catalog loader + resolver (global default + team rules)
- Temporal worker entrypoint to host lifecycle workflows

## Temporary User Bootstrap APIs (Before Full Review)

The following endpoints are temporary and are intended only to speed up
integration and end-to-end testing until the final user/team administration flow
is reviewed:

- `POST /control-plane/v1/users`
- `DELETE /control-plane/v1/users/{user_id}`

Team role assignment remains on existing team membership endpoints:

- `POST /control-plane/v1/teams/{team_id}/members` with `relation=member|manager|owner`
- `PATCH /control-plane/v1/teams/{team_id}/members/{user_id}` to change role

Important for these team membership write operations:

- Keycloak service account for client `control-plane` must have
  `realm-management/manage-users`.
- If missing, API now returns `403` with an explicit remediation message.

## Local run

```bash
cd control-plane-backend
make run
```

## Dev: Create test user without manual bearer token

When Control Plane API is running with user security enabled (`make run-prod`),
you can create a user with one command (token fetched automatically):

```bash
cd control-plane-backend
make create-test-user
```

By default, password values are resolved from `config/.env`:

- `KEYCLOAK_DEV_PASSWORD` falls back to `KEYCLOAK_CONTROL_PLANE_CLIENT_SECRET`
- `CP_NEW_USER_PASSWORD` falls back to `KEYCLOAK_CONTROL_PLANE_CLIENT_SECRET`

Optional overrides (CLI):

- `KEYCLOAK_DEV_USERNAME` (default: `alice`)
- `CP_NEW_USER_USERNAME` (default: `test1`)
- `CP_NEW_USER_EMAIL` (default: `test1@app.com`)
- `KEYCLOAK_DEV_PASSWORD`
- `CP_NEW_USER_PASSWORD`

## Local worker

```bash
cd control-plane-backend
make run-worker
```

Scheduler backend note:

- `scheduler.backend: temporal` => requires `make run-worker`.
- `scheduler.backend: memory` => runs lifecycle purge in-process (no Temporal server/worker required).

## Generate OpenAPI

```bash
cd control-plane-backend
make generate-openapi
```

## Policy catalog

By default, policy catalog file is loaded from:

`./config/conversation_policy_catalog.yaml`

You can override it in `config/configuration.yaml`.

## Team Member Deletion Endpoint

- `DELETE /control-plane/v1/teams/{team_id}/members/{user_id}`

Behavior:

- Removes user membership from Keycloak group.
- Removes team member/manager/owner relations from ReBAC.
- Resolves purge policy for `member_removed`.
- Enqueues matching session IDs in the purge queue with computed due date.
