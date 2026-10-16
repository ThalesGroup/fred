---
schema: 1
title: "Refresh frontend and agent runtime image dependencies"
impact: none
configuration: none
configuration_reason: "Only runtime image dependencies change; environment variables, chart values and application configuration remain compatible."
no_action_reason: "The refreshed frontend and agent images take effect through normal deployment, with no data migration or special restart order."
---
## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally. The frontend image uses nginx 1.31.7 and refreshed Alpine
packages. The agent image uses Python 3.12.15 on Debian stable and headless Impress
for PPT previews, replacing the full LibreOffice suite. Build-only pip copies and
their vendored dependencies are removed after the final locked installation.

Rebuilds should pull fresh bases and avoid stale cached package installation
layers when assessing newly published security fixes.

## Validation

Open the frontend, verify configured application proxy routes, and confirm any
deployment theme still loads. Run an agent turn and generate a PPT preview.
Scan the deployed image digests to verify their runtime packages; assess npm
dependencies separately from the nginx image.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.
An older image can reintroduce the vulnerabilities corrected by this update.

## Limitations

Scan results reflect the vulnerability database at scan time. This runtime update
does not change npm dependencies or remove their separately reported findings.
Debian packages without published stable fixes and the unchanged Temporal SDK's
embedded dependencies remain subject to their reported vulnerabilities.
