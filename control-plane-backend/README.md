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

## Local run

```bash
cd control-plane-backend
make run
```

## Local worker

```bash
cd control-plane-backend
make run-worker
```

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
