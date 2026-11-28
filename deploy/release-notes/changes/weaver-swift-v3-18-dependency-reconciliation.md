---
schema: 1
title: "Reconcile Swift release metadata and Python dependency locks"
impact: none
configuration: none
configuration_reason: "Only Python dependency locks and integration guidance change; Weaver package versions, charts and configuration remain unchanged."
no_action_reason: "The pyasn1 patch update is installed by the normal image build; no configuration or data migration is required."
---
## Applicability

Fresh Weaver installations built after the Swift v3.18.0 integration. Weaver
retains its own 5.x release history and does not support upgrading from Swift.

## Prerequisites

No additional prerequisites beyond the normal build and deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Build and deploy normally. Affected Python locks now resolve pyasn1 0.6.5
instead of 0.6.4. This change introduces no schema or data migration.

## Validation

Verify that the Agent Pod image reports pyasn1 0.6.5 with
`python -c 'from importlib.metadata import version; print(version("pyasn1"))'`.

## Rollback

Redeploy the previous image; no data rollback is required by this change.

## Limitations

Dependency lock and source quality checks do not establish deployed functional
acceptance. This is a targeted reconciliation, not an upgrade of every dependency.
