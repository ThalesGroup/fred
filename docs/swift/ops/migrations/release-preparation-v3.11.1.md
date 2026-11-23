---
schema: 1
title: "Prepare Fred release inputs and Python publication checks"
impact: none
configuration: none
configuration_reason: "Release notes, package versions, locks, chart appVersion values and publication checks change; deployment configuration does not."
no_action_reason: "The release inputs and publication checks do not change application behavior or data; the in-range change notes cover upgrade actions."
---

## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required by release preparation.

## Upgrade

Deploy Fred normally and follow any actions from the other in-range notes.

## Validation

Confirm the release notes and operator guide match the tagged version, the Python artifact dry run passes, and web-research changes select its CI job.

## Rollback

Use the normal rollback procedure; this preparation introduces no data migration.

## Limitations

Python package publication is a separate action from the code and chart tags.
