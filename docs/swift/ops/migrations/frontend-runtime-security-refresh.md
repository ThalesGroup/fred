---
schema: 1
title: "Refresh frontend nginx and Alpine security fixes"
impact: none
configuration: none
configuration_reason: "Only frontend runtime dependencies change; environment variables, chart values and proxy configuration remain compatible."
no_action_reason: "The refreshed nginx and Alpine packages take effect through normal frontend image deployment, with no data migration or special restart order."
---
## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally to replace the frontend image with nginx 1.31.7 and refreshed
Alpine packages. Rebuilds should pull fresh bases and avoid stale cached package
installation layers when assessing newly published security fixes.

## Validation

Open the frontend, verify configured application proxy routes, and confirm any
deployment theme still loads. Scan the deployed image digest to verify its
runtime packages; assess npm dependencies separately from the nginx image.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.
An older image can reintroduce the vulnerabilities corrected by this update.

## Limitations

Scan results reflect the vulnerability database at scan time. This runtime update
does not change npm dependencies or remove their separately reported findings.
