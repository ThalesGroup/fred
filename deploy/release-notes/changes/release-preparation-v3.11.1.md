---
schema: 1
title: "Port Swift Python publication checks to Weaver"
impact: none
configuration: none
configuration_reason: "Python publication checks, CI selection and dependency locks change; Weaver package and chart versions remain 5.0.0 and deployment configuration is unchanged."
no_action_reason: "Publication tooling and dependency updates require no configuration or data migration; normal deployment loads the updated dependencies."
---

## Applicability

Fresh Weaver installations and maintainers publishing Python packages.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required by release preparation.

## Upgrade

Deploy Fred normally and follow any actions from the other in-range notes.

## Validation

For a separately authorized Python release, pass the previous stable code tag as BASE_TAG to publication checks. Confirm older pending packages retain compatible dependency floors, newly prepared packages require current floors, and web-research changes select its CI job.

## Rollback

Use the normal rollback procedure; this preparation introduces no data migration.

## Limitations

Python package publication is a separate action from the code and chart tags.
