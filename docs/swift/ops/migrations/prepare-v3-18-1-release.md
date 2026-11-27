---
schema: 1
title: "Prepare Fred v3.18.1 release inputs and dependency locks"
impact: none
configuration: none
configuration_reason: "Release notes, Python package versions and dependency locks change; production configuration does not."
no_action_reason: "The dependency lock refresh and release inputs require no data migration or special upgrade step; the Word preview fix takes effect with a normal image rollout."
covers: [3d224fbba0d64faae91f1015e04cefb44dfddbfd]
---

## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

Confirm the spreadsheet capability installs from its locked dependencies and Word template PDF previews open after deployment.

## Rollback

Use the normal rollback procedure; these changes introduce no data migration.

## Limitations

Python package publication is separate from the code and chart tags.
