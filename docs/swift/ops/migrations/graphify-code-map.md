---
schema: 1
title: "Add a local Graphify code map for coding agents"
impact: none
configuration: none
configuration_reason: "Only repository-local developer tooling and instructions change; no runtime settings or chart values change."
no_action_reason: "The graph is generated only in developer checkouts and is ignored by Git; existing deployments and data are unchanged."
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

In a developer checkout with `uv` available, build the code graph as described in `docs/swift/platform/REPO_MAP.md` and run a bounded query. No production validation is required.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

The code graph is local to each checkout and is not a production service.
