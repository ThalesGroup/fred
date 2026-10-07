---
schema: 1
title: "Remove unused task tray and retired frontend flags"
impact: minor
configuration: production
configuration_reason: "The control-plane and worker Helm configuration schemas now accept only supported frontend flags. Bundled values now list the supported default-off flags and meet the stricter generated schema."
---
## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

Review private control-plane backend and worker values overlays for `platform.frontend.feature_flags` before installing the new chart.

## Configuration

Keep only `enableApplications` and `enableInformationSystems` under `platform.frontend.feature_flags`. Remove any other keys, including `enableAllResourceSpaces`, from both application overlays. The bundled Helm values already contain the supported default-off flags.

## Upgrade

Apply the overlay cleanup and validate the values against the new chart schema before the [coordinated release upgrade](2972-configurable-gcu-versions.md). This flag cleanup adds no data migration of its own.

## Validation

Confirm chart values validation passes. Check that `/control-plane/v1/frontend/bootstrap` exposes the two supported flags and that the admin Tasks and migration task pages still show task rows, statuses, and acknowledgements.

## Rollback

Restore the previous paired chart and code using the normal rollback procedure. Pruned overlay keys do not need to be restored.

## Limitations

Any private overlay that still sets an unsupported frontend flag fails strict chart validation until the key is removed.
