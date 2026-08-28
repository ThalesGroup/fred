# Fred Configuration And Policy Conventions

This page is the operational contract for developers working on Fred backends.

> [!IMPORTANT]
> **Access-control convention for all backends:**
> Keep the distinction explicit between global app RBAC roles (`admin`/`editor`/`viewer`) and team ReBAC relations (`team_admin`/`team_editor`/`team_analyst`/`team_member`).
> Team-level write operations must rely on team relations, not on app role shortcuts.
> A team's first `team_admin` is granted by the platform-admin-gated team-bootstrap action (`POST /teams`, RFC §28), not by post-install automation guessing at ownership.

It answers two practical questions:

1. How startup configuration is loaded.
2. How policy decisions are configured and enforced.

No extra conventions should be introduced outside this contract.

## Backends Covered

- `apps/fred-agents` (agent execution pod)
- `knowledge-flow-backend`
- `apps/control-plane-backend`

All three follow the same startup configuration contract.

## Startup Configuration Contract (Same In The 3 Backends)

At startup, each backend must do exactly this:

1. Load environment variables from `ENV_FILE` (default: `./config/.env`).
2. Resolve YAML configuration from `CONFIG_FILE` (default: `./config/configuration.yaml`).
3. Parse the YAML into the backend-specific pydantic `Configuration`.
4. Log which env file and config file were effectively loaded.

The shared helper used by backends is:

- `fred_core.ConfigFiles`

This is intentionally opinionated so DevOps has one rule only for startup config across services.

## Environment Variables (Do Not Rename)

These names are fixed for all backends:

- `ENV_FILE`
- `CONFIG_FILE`

Do not add service-specific aliases for config path loading.

Complete env inventory and ownership rules are documented in:

- [`docs/ENV_VARIABLES.md`](./ENV_VARIABLES.md)

## Expected Runtime Behavior

- `make run` starts API using the same `ENV_FILE/CONFIG_FILE` contract.
- `make run-worker` starts worker using the same `ENV_FILE/CONFIG_FILE` contract.
- API and worker logs must show the loaded env/config file paths.

## Policy Configuration In Fred

Fred policy behavior must come from files, not hardcoded values.

Current policy sources:

- Model/routing policy catalogs (agentic + knowledge-flow usage paths)
- Runtime-pod request policy in `apps/fred-agents` configuration, including
  `app.max_chat_input_chars` for the deployment-scoped chat-message limit
- Conversation lifecycle policy catalog in control-plane:
  - `apps/control-plane-backend/config/conversation_policy_catalog.yaml`

`app.max_chat_input_chars` is loaded once into `PodAppConfig`, enforced by the
runtime, and published read-only to managed chat through runtime-template and
execution-preparation metadata. It is not a database setting or a live
platform-admin preference.

When implementing behavior (for example purge delays), read from policy config and apply.
Do not embed retention windows or team-specific rules in code.

## Platform Feature Gates

Platform-wide staged features use typed boolean fields under
`platform.frontend.feature_flags`. Each feature has its own flag, and a missing
value is treated as `false`; one unfinished feature must never enable another.
Control-plane owns the value and publishes it through the authenticated
frontend bootstrap.

Frontend code consumes these fields through the shared feature-flag hook and
gate rather than repeating bootstrap lookups. A feature with backend routes or
gateway paths must also fail closed at those boundaries. Hiding a frontend
control is not authorization, so the normal permission checks still apply when
the feature is enabled.

`enableApplications` is the bundled-applications gate and defaults to `false`.
While it is off, application routes, catalogs, administration controls, and
`/app-services` gateway paths are unavailable. Installed manifests and existing
team grants remain intact so enabling the flag does not require rebuilding Fred
or recreating entitlements.

The control-plane field is the single authoritative deployment setting. The
Fred Helm chart derives the frontend container's
`FRONTEND_ENABLE_APPLICATIONS` value from it so the backend and gateway cannot
be configured independently through chart values. The environment variable is
still accepted directly for local Vite and standalone-container parity, where
the operator must keep it aligned with the control-plane field; it also defaults
to `false`.

## Bundled Application Configuration

`apps/applications/<application-id>/fred-app.json` is a non-secret, build-time
installation manifest. Each package keeps that manifest beside a `frontend/`
module and an optional `backend/` service boundary. One generator derives the
frontend registry, localized resources, runtime service contract, and packaged
control-plane catalog. The frontend registry and runtime service contract are
tracked generated artifacts and must match the manifests in quality gates. The
Control Plane catalog is Git-ignored and regenerated before Control Plane
builds, tests, packaging, and image creation. It must never be committed or
edited independently.

The manifest declares only identity, display metadata, version compatibility,
and `service_required`. It cannot carry an upstream address, token, credential,
arbitrary header, raw HTML, or executable module URL.

The `frontend/` directory is compiled into Fred's frontend image. A backend is
an independently built application service and is needed only when the manifest
and deployment require it. The included placeholder sets `service_required` to
`false`; its `backend/` directory contains no runtime implementation.

Deployment owns the server-side application service map through
`FRONTEND_APPLICATION_UPSTREAMS_JSON`, a JSON object whose keys are installed
application ids and whose values are HTTP(S) upstream roots. Container startup
rejects unknown ids, unsafe URLs, and a missing mapping for any
`service_required` application. A service-free or optional application may
have no mapping; Fred still starts and its service path returns a generic 503.
Unknown `/app-services/<id>/...` paths return 404. The mapping is routing
configuration, not a secrets channel.

## When Adding A New Backend

Use the same startup contract immediately:

1. Use `ConfigFiles` for env/config path loading.
2. Keep `ENV_FILE` and `CONFIG_FILE` as-is.
3. Parse into local pydantic config model.
4. Log loaded env/config paths.

If this contract cannot be followed, document the reason in this file before merging.
