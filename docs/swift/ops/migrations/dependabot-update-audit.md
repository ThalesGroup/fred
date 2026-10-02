---
schema: 1
title: "Audit the five Dependabot dependency updates"
impact: none
configuration: none
configuration_reason: "The reviewed npm package and Python lock updates add no configuration keys or defaults."
no_action_reason: "These dependency updates change packaged libraries only; existing data, public APIs and deployment order are unchanged."
covers:
  - 78d2e1552fb670e8606ad48058061f98d34653ae
  - 89e8cce8539f056bd166921af5bc896d15637547
  - b22104e1f242f98f11cbb2c0ea5efa4987ae7de9
  - 7c7de5845efb838348bb71358f574e43c4171f04
  - c2f775cd7455e05f124047b70b42c8b91aa5cc06
---
## Applicability

Deployments upgrading frontend assets and Python service images in this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally. The reviewed commits update the frontend editor and npm dependencies, plus PyJWT and urllib3 locks across Python packages. No data migration or re-ingestion is required.

## Validation

Confirm the frontend loads, an authenticated request succeeds, and a representative document opens.

## Rollback

Use the normal image and asset rollback procedure; no data migration is introduced by these updates.

## Limitations

Services built from older locks retain their previous dependency versions.
