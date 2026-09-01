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

## Application Registration

Applications are registered in deployment configuration, not built into Fred.
Each one ships as its own UI container image, and optionally its own API, built
and released by the team that owns it. Fred compiles no application code, so
there is no manifest, no generator, and no generated artifact to keep in sync.

Registration has two halves, one per process. `app_id` is the only key they
share, and it must match across them:

- **Control plane** — `platform.application_sources[]`, expressed like
  `platform.runtime_catalog_sources[]`. Each entry carries `app_id`,
  `ui_prefix`, `version`, `icon`, localized `display_name`/`description`, and
  `enabled`. It owns the catalog the API returns and the `app__<app_id>`
  capability that team authorization is granted against, and it registers no
  proxy upstream at all. `ui_prefix` is browser-facing: exactly
  `/apps/<app_id>` while the UI is served from Fred's origin — config load
  rejects any other own-origin path, because the gateway routes on that
  segment and nothing else can reach the application — or an absolute `https`
  URL once the UI is served from its own origin. Nothing may assume the
  former.
- **Frontend gateway** — `FRONTEND_APPLICATIONS_JSON`, a JSON array of
  `{app_id, ui_upstream, service_upstream?, service_required?}`. These are the
  server-side addresses nginx proxies to and they never reach the browser. The
  two halves are separate because the control plane never proxies and the
  gateway never authorizes.

Because the halves are separate, an `app_id` registered in one and not the
other is not detected at startup. Forward (control plane only): the
application appears in the catalog and its frame 404s. Reverse (gateway only):
the prefixes proxy for an application no team was ever granted — the gateway
performs no authorization of its own, so keep the gateway list a subset of the
catalog. `enabled: false` withdraws an application from the catalog but leaves
its gateway routes serving; remove both halves to retire one.

Neither half carries a token, credential, arbitrary header, or raw HTML.
Registration is routing and catalog configuration, not a secrets channel.

Container startup rejects duplicate ids and unsafe URLs, and the gateway
refuses to start when a `service_required` application has no
`service_upstream` — a permanent 503 is a deployment mistake, not a runtime
state to serve. That rule lives in the gateway alone, since it is the process
that would serve the 503. A UI-only
application simply omits `service_upstream`: Fred starts, `/apps/<app_id>/`
serves, and `/app-services/<app_id>/...` returns a generic 503. Unknown ids
return 404 in both namespaces, as does everything under either prefix while
the feature switch is off.

## When Adding A New Backend

Use the same startup contract immediately:

1. Use `ConfigFiles` for env/config path loading.
2. Keep `ENV_FILE` and `CONFIG_FILE` as-is.
3. Parse into local pydantic config model.
4. Log loaded env/config paths.

If this contract cannot be followed, document the reason in this file before merging.
