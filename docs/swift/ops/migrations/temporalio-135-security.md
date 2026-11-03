---
schema: 1
title: "Upgrade the Temporal Python SDK to 1.35.0"
impact: none
configuration: none
configuration_reason: "Only the Temporal Python SDK dependency floor and locked artifacts change; no runtime or Helm settings change."
no_action_reason: "Normal image rebuild and deployment install the updated SDK; existing workflows, storage and server configuration require no migration."
---
## Applicability

Fred Python packages and backend images containing the Temporal SDK.

## Prerequisites

Use images rebuilt from the updated lockfiles. No additional operator prerequisites.

## Configuration

No configuration changes are required.

## Upgrade

Deploy the rebuilt Fred images normally. The direct dependency floor is 1.35.0 and every affected lockfile resolves temporalio 1.35.0.

## Validation

Verify the SDK reports version 1.35.0 and workers connect normally. Rescan rebuilt images to confirm whether the reported vulnerability is cleared. Upstream release notes: https://github.com/temporalio/sdk-python/releases/tag/1.35.0.

## Rollback

The previous images can be restored without a data migration, but doing so restores the older SDK and its security exposure.

## Limitations

Updating source constraints does not repair already published images; rebuild and redeploy them. The upstream release contains security fixes in Rust dependencies bundled in the Python wheel. No image vulnerability scan was run as part of this dependency update.
