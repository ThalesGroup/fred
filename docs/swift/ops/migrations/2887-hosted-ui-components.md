---
schema: 1
title: "Shared UI components and retirement of the built-in evaluator"
impact: minor
configuration: none
configuration_reason: "No configuration keys or defaults change. Deployments using built-in evaluations must register the external evaluator using the existing application configuration."
---
## Applicability

Fred deployments using built-in evaluations before upgrading to v3.2.0, including
the evaluator removal tracked by #2904. Deployments not using evaluations need
no evaluator setup.

## Prerequisites

For deployments using evaluations, this migration is blocked until the standalone evaluator enforces team membership and application grants on every API operation, including direct access through the legacy `/evaluation/` proxy. In addition, preserve the operation-specific ReBAC checks in the [product contract](../../design/CONTROL-PLANE-PRODUCT-CONTRACT.md): `CAN_READ` to view evaluations, `CAN_UPDATE_AGENTS` to create or cancel them, and `CAN_READ_CONVERSATIONS` to evaluate real conversations. Team membership and the application grant do not replace those permissions. Apps admission and the application gateway do not provide this API authorization. Do not treat the currently documented authentication-only evaluator as meeting this prerequisite. Verify the deployed evaluator implementation before rollout.

After that prerequisite is met, deploy and register the standalone fred-agent-evaluator application before upgrading Fred. Follow the existing [application deployment contract](../../platform/FORKING_GUIDE.md); grant the intended teams access through the existing application permissions. Preserve the evaluator service and its database.

## Configuration

No new configuration fields are introduced. Existing application registration and ingress/proxy settings must expose the evaluator UI and API. Deployments already using the evaluator through Apps need no further configuration. Deployments not using evaluations can upgrade normally.

## Upgrade

Only after the authorization prerequisite is verified, validate that an authorized team can open the evaluator through Apps, then deploy Fred. The built-in Evaluations settings entry, screens and direct evaluator task polling are removed. Use Apps to inspect evaluation runs and progress; the old settings URL falls back to Members.

## Validation

Confirm Apps opens the evaluator for an authorized team. Independently verify that direct API requests from authenticated users without the target team membership or application grant are denied, through both the application gateway and legacy `/evaluation/` path. For a member of a granted team, also verify denial of viewing without `CAN_READ`, creation/cancellation without `CAN_UPDATE_AGENTS`, and real-conversation evaluation without `CAN_READ_CONVERSATIONS`, through both paths; verify permitted operations succeed for appropriately authorized users. An Apps admission check alone is insufficient; failed or missing API authorization blocks rollout. Verify Members and Activity still work and Fred no longer calls `/evaluation/v1` directly. The shared UI package must pass archive/consumer validation; StatusBadge and other reusable exports remain available.

In the evaluation application, click a run row to open its preview, close the case drawer using its localized close action, and inspect outcome KPI values in both themes.

## Rollback

Restore the previous Fred frontend image to recover the built-in screens. Keep the evaluator service, application registration and data; this change introduces no data migration or deletion.

## Limitations

Publishing the frontend npm packages is a separate operation; the final
candidates in this release are aligned on alpha.4. The UI package's hosted surface is limited to what hosted applications use: `DataTable` without row selection, a single overlay `InlineDrawer`, and `ToastProvider`/`useToast`; `TablePagination` and the direct `Toast` are not exported. The removal does not publish packages, deploy the external evaluator, change evaluation permissions or delete historical evaluations.
