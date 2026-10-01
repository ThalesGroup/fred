---
schema: 1
title: "Replace the token-exchange RFC with a current delegated execution doc and remove stale root notes"
impact: none
configuration: none
configuration_reason: "Only documentation and code comments change; no configuration keys, defaults or chart values change."
no_action_reason: "No runtime behavior, API, data or permission changes; the edited Python files differ only in comments and docstrings."
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

Open `docs/swift/platform/DELEGATED-EXECUTION.md` and check that its links resolve.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
