## Why

Fred's local deployment currently combines image builds, installation values, Helm commands and product bootstrap in a factory-owned script. Use Helmfile to describe the installation rather than introducing a custom deployment blueprint and parser.

Tracking: https://github.com/ThalesGroup/fred/issues/2957

## What Changes

- Add a standard Helmfile state in `fred-deployment-factory` for the existing `fred-app` release, using Fred's existing chart and factory installation values.
- Move Fred image preparation and strictly product-specific operations into Fred; keep cluster targeting, image import and protected Helm recovery in the factory.
- Provide explicit build/deploy and validation commands. Validation must not build images or mutate the cluster; deployment must lint and render effective values before cluster mutations.
- Preserve four content-tagged images, both workers' reuse of backend images, model-key refresh, dashboards and initial bootstrap guidance.
- **BREAKING**: retire `k3d-fred` and its old launcher without an alias; document the Helmfile-based replacement.
- Limit this slice to Fred on the existing infrastructure. Maxwell, evaluator migration and migration of `k3d-up` into Helmfile are excluded.

## Capabilities

### New Capabilities

- `local-helm-deployment`: Fred's local image preparation and safe, repeatable Helmfile deployment with factory-owned installation values.

### Modified Capabilities

None. No existing durable deployment capability spec was found.

## Impact

Fred: `deploy/`, build helpers/Make targets, relevant current deployment documentation, targeted tests and an English migration note. Factory companion work: Helmfile state, Make targets, replacement orchestration, current guides and targeted tests. Helmfile is a new local prerequisite. Existing charts, releases, namespaces, storage and application APIs retain their identities. Preserve factory's unrelated uncommitted observability edits.
