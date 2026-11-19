---
schema: 1
title: "Prepare Fred v3.13.0 release and account for maintenance updates"
impact: none
configuration: none
configuration_reason: "Release metadata, a README license link, and the mail-parser lockfile update do not change configuration keys or defaults."
no_action_reason: "The mail-parser update is installed with the normal Knowledge Flow image, and the README and release metadata changes require no deployment action."
covers:
  - a9b80c504413c84d1598165c4fc8599b1cdd639b
  - 5ee79587f5ea3f44ade8bb45c5aa5792c41003ce
  - f3edaebac0d03d4e9ae681bb0053668663ff1f47
---

## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the procedures from the other in-range notes.

## Configuration

No configuration changes are required for these maintenance contributions.

## Upgrade

Deploy the images and chart normally after completing any steps in the consolidated release guide.

## Validation

Check that Knowledge Flow starts with the updated dependency and the README license link resolves to the repository license.

## Rollback

Use the normal rollback procedure; these contributions add no data migration.

## Limitations

The dependency update and documentation correction have no separate operational limitations.
