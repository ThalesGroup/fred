---
schema: 1
title: "Prepare Fred 3.7.1 release metadata and Python packages"
impact: none
configuration: none
configuration_reason: "Only release documentation, shared Python package versions and dependency floors, synchronized locks, and pod chart appVersion metadata change; no production configuration key or default changes."
no_action_reason: "The shared Python packages advance to 4.5.4 with synchronized locks and compatible dependency floors. Normal deployment is enough; this preparation adds no data migration, configuration change, re-ingestion or special restart order. The Ubuntu image note describes the separate compatibility check for custom derived images."
---
## Applicability

Fred deployments upgrading from 3.7.0 to 3.7.1.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required. The agent-pod and knowledge-base chart
appVersion metadata follows the prepared fred-runtime and fred-sdk versions.

## Upgrade

Deploy Fred normally. No document re-ingestion or optional feature activation is
required. Review the Ubuntu image note before rebuilding custom derived images.

## Validation

Confirm the 3.7.1 entry appears in the release history. Run an agent turn and,
with a Mistral model, verify a long task executes its tools and returns an answer.

## Rollback

Redeploy the previous matching images and charts through the normal rollback
procedure. This release preparation introduces no data migration.

## Limitations

Python packages have independent versions. Image and chart publication does not
publish these packages to PyPI; external consumers need a separate authorized
package publication before resolving the new coordinates.
