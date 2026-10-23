---
schema: 1
title: "Advance the shared Python libraries to 4.5.9 for v3.9.2"
impact: none
configuration: none
configuration_reason: "Only Python package versions, internal dependency floors, locks and the pod chart appVersion change; no deployment setting or default is introduced."
no_action_reason: "fred-runtime 4.5.8 was published before the runtime and capability downgrade command (#3225) merged; 4.5.9 ships it, and normal deployment includes it."
---

## Applicability

Projects installing fred-core, fred-sdk or fred-runtime from PyPI. fred-runtime 4.5.9 adds the downgrade command described in the runtime and capability downgrade note; fred-core and fred-sdk advance with it without code change.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required. Projects depending on the Fred libraries update to 4.5.9 once published.

## Validation

`make validate-python-release` lists fred-core, fred-sdk and fred-runtime 4.5.9 to publish, and every other package identical to PyPI.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
