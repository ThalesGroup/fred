---
schema: 1
title: "Prepare Fred v3.9.1 and audit dependency updates"
impact: none
configuration: none
configuration_reason: "Release notes, package versions and locks change, but no deployment setting or default is introduced by this preparation or the covered dependency update."
no_action_reason: "The covered dependency update changes only the fred-sdk and fred-runtime lockfiles; normal deployment includes it."
covers:
  - 0d1c31b857bb816559d67664c30a584f951f511c
---

## Applicability

Fred deployments upgrading from v3.9.0. The covered commit updates uv and certifi in the fred-sdk and fred-runtime lockfiles; uv was then aligned on 0.13.5 everywhere by #3243.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required for this dependency update or release preparation.

## Upgrade

Deploy the reviewed images and chart normally, after completing any required actions from the other notes in this release. No extra action is needed for the covered dependency update.

## Validation

The release PR validates package artifacts and locked dependency installation.

## Rollback

Use the normal release rollback procedure. This update introduces no data migration.

## Limitations

This note covers only the listed dependency commit and release preparation. Other release changes have separate notes.
