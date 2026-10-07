---
schema: 1
title: "Retire the legacy Python GCU version enum"
impact: minor
configuration: none
configuration_reason: "The app.gcu_version string, database column and HTTP contracts are unchanged."
---
## Applicability

Fred deployments upgrading from v3.2.0 and Python consumers of the user-store API.

## Prerequisites

Check custom Python integrations for imports of `GcuVersionsType` or enum inputs to `update_gcu_version`.

## Configuration

No configuration changes are required; existing configured version strings remain valid.

## Upgrade

If an external Python consumer imports `GcuVersionsType`, remove that import and replace `GcuVersionsType.V1` with `"v1"` or the configured version string. Pass strings to `update_gcu_version`. Repository callers already do this. Deploy Fred normally; no new database migration or special deployment order is required.

## Validation

Accept the configured terms and confirm `GET /user` reports the same version string in `cguValidated`. Confirm custom Python integrations import and record acceptance successfully.

## Rollback

Use the normal rollback procedure to v3.2.0. Its store also accepts string inputs, and the database representation is unchanged.

## Limitations

`GcuVersionsType` is no longer importable from the user model, `fred_core.users` or `fred_core`. Published v3.2.0 notes describe the compatibility available in that release; this note retires it for the next release. Earlier database upgrade and guarded-downgrade procedures still apply when crossing their original version boundary.
