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
cd apps/control-plane-backend
make run
```

## Local CLI

The control-plane backend now exposes a developer/operator CLI similar in
spirit to `fred-agent-chat`, but focused on product/admin flows:

```bash
cd apps/control-plane-backend
make cli
```

The CLI follows the same startup contract as the API:

- it resolves `ENV_FILE` and `CONFIG_FILE` the same way as backend startup
- it auto-discovers Keycloak login settings from backend config when
  `security.user.enabled: true`
- it also works in no-security local mode when user security is disabled

It supports both:

- interactive mode: `make cli`
- one-shot mode: `make cli ARGS="teams"`

Useful one-shot examples:

```bash
# Show local command help without depending on the frontend
make cli ARGS="/help"

# List visible teams
make cli ARGS="teams"

# Start already scoped to one team
.venv/bin/uv run fred-control-plane-cli --team-id fredlab
```

Useful interactive commands:

- `/help`
- `/whoami`
- `/bootstrap`
- `/teams`
- `/team <team_id|team_name>`
- `/team-info [team_id|team_name]`
- `/members [team_id|team_name]`
- `/templates`
- `/instances`
- `/enroll <template_id> [display_name]`
- `/runtime <agent_instance_id>`
- `/sessions [team_id|team_name]`
- `/prepare <agent_instance_id>`
- `/policy summary`
- `/policy resolve [team_id|team_name] [member_removed|member_rejoined]`
- `/lifecycle run-once [dry-run|live] [batch_size]`

Team-scoped commands use either:

- the current shell context set by `/team <team_id>`
- or an initial scope passed at startup with `--team-id <team_id>`

For team selection, the CLI accepts either:

- the canonical `team_id`
- or the visible team name shown by `/teams` when it is unique

When Keycloak-backed user security is enabled, the CLI also supports:

- `/login` for browser PKCE login
- `/login-password [user]` for local direct-grant fallback
- `/logout` to clear the cached CLI session

## Dev: Create test user without manual bearer token

When Control Plane API is running with user security enabled (`make run-prod`),
you can create a user with one command (token fetched automatically):

```bash
cd apps/control-plane-backend
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
cd apps/control-plane-backend
make run-worker
```

Scheduler backend note:

- `scheduler.backend: temporal` => requires `make run-worker`.
- `scheduler.backend: memory` => runs lifecycle purge in-process (no Temporal server/worker required).

## Generate OpenAPI

```bash
cd apps/control-plane-backend
make generate-openapi
```

## Coverage Priorities

Current coverage is good enough to iterate, but the next useful gains should
target product behavior first, not infrastructure wrappers.

Priority order:

1. `control_plane_backend/cli/main.py`
   - cover the command matrix still lightly tested:
     `/unbind`, `/runtime`, `/sessions`, `/prepare`, `/policy`,
     `/lifecycle`, login branches, and HTTP error formatting
2. `control_plane_backend/users/service.py`
   - cover no-Keycloak mode, `404`/`409` branches, pagination in
     `_fetch_all_users`, and fallback behavior in `get_users_by_ids`
3. SQLite-backed stores
   - `control_plane_backend/teams/metadata_store.py`
   - `control_plane_backend/sessions/store.py`
   - add offline tests for create/update/delete, empty upsert, and ordering
4. `control_plane_backend/app/context.py`
   - cover lazy getters, scheduler backend resolution, and `shutdown()`
5. Low-cost compatibility wrappers
   - `control_plane_backend/core/policies/*.py`

Deliberately lower priority:

- `control_plane_backend/main_worker.py`
- `control_plane_backend/scheduler/temporal/worker.py`
- `control_plane_backend/scheduler/temporal/workflow.py`

These are better validated through integration tests and should stay out of the
default offline unit-test target unless they can be exercised without external
services.

Testing rules for this project:

- keep default tests offline
- prefer fakes or SQLite over live Keycloak/Temporal/Postgres
- mark external-service scenarios with `@pytest.mark.integration`

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
