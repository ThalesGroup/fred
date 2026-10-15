---
schema: 1
title: "Prepare independently versioned Python packages for releases"
impact: none
configuration: none
configuration_reason: "Only repository release tooling, package version guidance and validation change; no deployed configuration changes."
no_action_reason: "Existing deployments need no action because this change prepares future Python package releases without changing running code or data."
---
## Applicability

Fred maintainers preparing Python distributions for future releases.

## Prerequisites

No additional deployment prerequisites.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally. Package preparation and PyPI publication remain maintainer
operations outside the deployment procedure.

## Validation

For the next release, verify the reviewed package version map, capability manifest
compatibility and synchronized uv lockfiles before tag approval.

## Rollback

Revert the release-tooling change before publication. Published package versions
are immutable and require a later coordinate for corrections.

## Limitations

This change does not publish Python packages or create a Fred release.
