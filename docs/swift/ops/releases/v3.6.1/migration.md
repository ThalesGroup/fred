# Migration guide — v3.6.1

Upgrade from: `code/v3.6.0`
Operational impact: **none** (minimum version: `3.6.1`).

Review these procedures together in the listed dependency order before deployment. Customer-specific values remain in their private repositories; Fred chart values are the production reference. Configuration files named configuration_prod.yaml are for local development only.

No-operation declarations describe ordinary deployment only. Conditional activation steps still require preparation. Validate combined upgrade and rollback in staging before production.

## Coordinated v3.6.1 upgrade and rollback

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.6.1/docs/swift/ops/migrations/000-v3-6-1-release-preparation.md)

Rendered Kubernetes manifests, application behaviour and data are unchanged from v3.6.0; deploying the paired v3.6.1 code and chart is enough.

See the source note for applicability, validation and rollback.

## Fred's k3d values move to fred-deployment-factory, which deploys published releases

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.6.1/docs/swift/ops/migrations/2957-k3d-published-release.md)

No deployed workload, data or API changes; only the local k3d command changes, to make k3d-app APP=fred [DIR=<fred checkout>].

See the source note for applicability, validation and rollback.

## The published charts carry a README, an icon and project metadata

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.6.1/docs/swift/ops/migrations/artifacthub-chart-presentation.md)

Rendered Kubernetes manifests are identical; the change only affects how registries such as Artifact Hub present the charts.

See the source note for applicability, validation and rollback.
