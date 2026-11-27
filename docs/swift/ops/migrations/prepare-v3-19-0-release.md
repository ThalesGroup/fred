---
schema: 1
title: "Prepare Fred v3.19.0 release inputs and dependency locks"
impact: none
configuration: none
configuration_reason: "This contribution updates release notes, the operator guide, Python package versions, chart appVersion metadata, and dependency locks without changing runtime configuration."
no_action_reason: "The release preparation itself changes no deployed data or behavior; normal deployment suffices for these inputs."
---

## Applicability

Existing Fred deployments upgrading to v3.19.0.

## Prerequisites

Follow the other procedures in this release guide for any affected model profiles.

## Configuration

No configuration changes are required for the release preparation itself.

## Upgrade

Deploy the approved images and chart normally after reviewing the other release procedures.

## Validation

Confirm the deployed version is v3.19.0 and the dependency locks install with `uv sync --locked` in affected Python projects.

## Rollback

Use the normal rollback procedure; this contribution adds no data migration.

## Limitations

Python package publication is a separate action from image and chart publication.
