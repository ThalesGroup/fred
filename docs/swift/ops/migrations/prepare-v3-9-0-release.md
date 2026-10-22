---
schema: 1
title: "Prepare Fred v3.9.0 and audit dependency updates"
impact: none
configuration: none
configuration_reason: "Release notes, package versions and locks change, but no deployment setting or default is introduced by this preparation or the covered dependency updates."
no_action_reason: "The covered dependency updates need no configuration or data migration; normal deployment includes them."
after: [3211-compose-chart-registrations]
covers:
  - 5dd26a0c30e67d2b219917d39b0136324d92ca0e
  - d574a0347b9043f171b139d62dc52636191d981a
  - 80b7ef118f03ef4420019dbb5635aae0a245906a
  - 0141444afcf095b3053e793dc5323517390ebe64
  - def8d239eb3baae9332be75431738f640e8f850b
---

## Applicability

Fred deployments upgrading from v3.8.0. The covered commits update Go dependencies in the local benchmark tool, npm build and test dependencies, Python lockfile dependencies, and Pillow in the agents image.

## Prerequisites

No additional deployment prerequisites. Building the local Go benchmark tool now requires Go 1.24.

## Configuration

No configuration changes are required for these dependency updates or release preparation.

## Upgrade

Deploy the reviewed images and chart normally, after completing any required actions from the other notes in this release. No extra action is needed for the covered dependency updates.

## Validation

Confirm the agents image starts and image processing still works. Confirm the frontend loads and renders mathematical expressions. The release PR validates package artifacts and locked dependency installation.

## Rollback

Use the normal release rollback procedure. These updates introduce no data migration.

## Limitations

This note covers only the five listed dependency commits and release preparation. Other release changes have separate notes and may require operator actions.
