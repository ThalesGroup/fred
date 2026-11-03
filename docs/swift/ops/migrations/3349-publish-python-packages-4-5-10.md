---
schema: 1
title: "Publish the shared Python libraries 4.5.10 with structured MCP result support"
impact: none
configuration: none
configuration_reason: "Only Python package versions, internal dependency floors, locks and pod chart appVersion metadata change; no deployment setting or default is introduced."
no_action_reason: "fred-runtime 4.5.10 includes the structured MCP result normalization from #3325/#3326. No data migration, configuration change or re-ingestion is required."
---

## Applicability

Projects installing fred-core, fred-sdk or fred-runtime from PyPI.

fred-runtime 4.5.10 includes the structured MCP result normalization introduced
by #3325 and #3326. fred-core and fred-sdk are published as part of the shared
Python library release set.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Projects depending on the Fred Python libraries can update to 4.5.10 once
published. No additional operator or user action is required.

## Validation

`make publish-libs-dry-run` identifies fred-core, fred-sdk and fred-runtime
4.5.10 for publication, while the capability packages are already present on
PyPI.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

Python package publication remains a separate maintainer operation after this
preparation PR is merged.
