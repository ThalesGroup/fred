## Why

Repeated first-user tests need empty Fred data without rebuilding the local k3d infrastructure. An application uninstall preserves that data, while a cluster wipe also destroys identities and reloads images.

Tracking: https://github.com/ThalesGroup/fred/issues/3092 (manager journey test tooling).

## What Changes

- Add `make k3d-app-reset DIR=<checkout>` to the factory, dispatching to a product-owned optional reset hook.
- Fred's hook previews the operation by default. Explicit execution resets the dedicated local Fred installation, including manager when installed, without rebuilding images or deleting the cluster or PVCs.
- Preserve Keycloak identities, clients, credentials, observability and unrelated infrastructure databases. Reset Fred SQL data, OpenFGA authorization, Temporal jobs, Fred indexes and content storage together.
- Refuse shared installations or unsupported storage configurations before any mutation. Keep applications stopped on a cleanup failure and support retry.

## Capabilities

### New Capabilities

- `local-helm-deployment`: add reset requirements to the existing deployment capability introduced by the separate `deploy-fred-with-helmfile` change. This change does not complete that change's outstanding deployment tasks.

### Modified Capabilities

None.

## Impact

Factory Makefile, generic hook dispatch, existing local-development guides and command tests. Fred `deploy/k3d/` reset tooling and tests, operations documentation and migration note. No product API, Rust code, schema migration or infrastructure chart changes. No execution against the developer's populated cluster during implementation.
