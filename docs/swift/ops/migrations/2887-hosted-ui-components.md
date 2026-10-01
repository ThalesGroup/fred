---
schema: 1
title: "Shared UI components and retirement of the built-in evaluator"
impact: minor
configuration: none
configuration_reason: "No configuration keys or defaults change. Deployments using built-in evaluations must register the external evaluator using the existing application configuration."
---
## Applicability

Fred deployments upgrading with PR #2890, including the built-in evaluator removal tracked by #2904.

## Prerequisites

For deployments using evaluations, deploy and register the standalone fred-agent-evaluator application before upgrading Fred. Follow the existing [application deployment contract](../../platform/FORKING_GUIDE.md); grant the intended teams access through the existing application permissions. Preserve the evaluator service and its database.

## Configuration

No new configuration fields are introduced. Existing application registration and ingress/proxy settings must expose the evaluator UI and API. Deployments already using the evaluator through Apps need no further configuration. Deployments not using evaluations can upgrade normally.

## Upgrade

Validate that an authorized team can open the evaluator through Apps, then deploy Fred. The built-in Evaluations settings entry, screens and direct evaluator task polling are removed. Use Apps to inspect evaluation runs and progress; the old settings URL falls back to Members.

## Validation

Confirm Apps opens the evaluator for an authorized team, while unauthorized teams retain the existing admission restrictions. Verify Members and Activity still work and Fred no longer calls `/evaluation/v1` directly. The shared UI package must pass archive/consumer validation; StatusBadge and other reusable exports remain available.

## Rollback

Restore the previous Fred frontend image to recover the built-in screens. Keep the evaluator service, application registration and data; this change introduces no data migration or deletion.

## Limitations

Publishing the alpha.3 npm package is a separate operation. The removal does not publish packages, deploy the external evaluator, change evaluation permissions or delete historical evaluations.
