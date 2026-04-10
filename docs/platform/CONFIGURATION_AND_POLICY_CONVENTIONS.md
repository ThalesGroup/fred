# Fred Configuration And Policy Conventions

This page is the operational contract for developers working on Fred backends.

> [!IMPORTANT]
> **Access-control convention for all backends:**
> Keep the distinction explicit between global app RBAC roles (`admin`/`editor`/`viewer`) and team ReBAC relations (`owner`/`manager`/`member`).
> Team-level write operations must rely on team relations, not on app role shortcuts.
> Initial `owner`/`manager` team assignments must be provisioned by deployment post-install automation.

It answers two practical questions:

1. How startup configuration is loaded.
2. How policy decisions are configured and enforced.

No extra conventions should be introduced outside this contract.

## Backends Covered

- `agentic-backend`
- `knowledge-flow-backend`
- `control-plane-backend`

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
- Conversation lifecycle policy catalog in control-plane:
  - `control-plane-backend/config/conversation_policy_catalog.yaml`

When implementing behavior (for example purge delays), read from policy config and apply.
Do not embed retention windows or team-specific rules in code.

## When Adding A New Backend

Use the same startup contract immediately:

1. Use `ConfigFiles` for env/config path loading.
2. Keep `ENV_FILE` and `CONFIG_FILE` as-is.
3. Parse into local pydantic config model.
4. Log loaded env/config paths.

If this contract cannot be followed, document the reason in this file before merging.
