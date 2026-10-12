---
schema: 1
title: "Retire the legacy Python GCU version enum"
impact: minor
configuration: none
configuration_reason: "The app.gcu_version string, database column and HTTP contracts are unchanged."
---
## Applicability

Running Fred v3.2.0 deployments, new installations and Python consumers of the user-store API. Earlier installations still need the original enum-to-text migration when upgrading through v3.2.0.

## Prerequisites

Check custom Python integrations for imports of `GcuVersionsType` or enum inputs to `update_gcu_version`.

## Configuration

No configuration changes are required; existing configured version strings remain valid.

## Upgrade

If an external Python consumer imports `GcuVersionsType`, remove that import and replace `GcuVersionsType.V1` with `"v1"` or the configured version string. Pass strings to `update_gcu_version`. Repository callers already do this.

- Running v3.2.0 pods are unaffected until their images are upgraded. For the retirement in this note, normal rolling deployment is sufficient: both versions read and write the same text column, so there is no additional drain, restart order or database revision.
- New installations use the normal migration chain and configure `app.gcu_version` as a string. Historical enum-to-text conversion remains in that chain and does not import the removed Python class.
- Upgrades from before v3.2.0 still follow the [original CGU conversion procedure](2972-configurable-gcu-versions.md), including stopping old enum-based readers during schema conversion. This retirement does not relax that earlier requirement.

This change does not require users to accept the terms again. Reacceptance remains tied to a change in the configured version string.

## Validation

Accept the configured terms and confirm `GET /user` reports the same version string in `cguValidated`. Confirm custom Python integrations import and record acceptance successfully.

## Rollback

Use the normal rollback procedure to v3.2.0. Its store also accepts string inputs, and the database representation is unchanged.

## Limitations

`GcuVersionsType` is no longer importable from the user model, `fred_core.users` or `fred_core`. Published v3.2.0 notes describe the compatibility available in that release; this note retires it for the next release. Earlier database upgrade and guarded-downgrade procedures still apply when crossing their original version boundary.
