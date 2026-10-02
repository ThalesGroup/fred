---
schema: 1
title: "Shared UI components and retirement of the built-in evaluator"
impact: minor
configuration: production
configuration_scope: deployment-values
configuration_reason: "Affected deployments must update existing production Helm application catalog, FRONTEND_APPLICATIONS_JSON and ingress/proxy values to register and expose the external evaluator."
---
## Applicability

Fred deployments upgrading with PR #2890, including the built-in evaluator removal tracked by #2904, and consumers of the unpublished UI alpha.3 candidate.

## Prerequisites

For deployments using evaluations, this migration is blocked until the standalone evaluator enforces team membership and application grants on every API operation, including direct access through the legacy `/evaluation/` proxy. In addition, preserve the operation-specific ReBAC checks in the [product contract](../../design/CONTROL-PLANE-PRODUCT-CONTRACT.md): `CAN_READ` to view evaluations, `CAN_UPDATE_AGENTS` to create or cancel them, and `CAN_READ_CONVERSATIONS` to evaluate real conversations. Team membership and the application grant do not replace those permissions. Apps admission and the application gateway do not provide this API authorization. Do not treat the currently documented authentication-only evaluator as meeting this prerequisite. Verify the deployed evaluator implementation before rollout.

After that prerequisite is met, deploy and register the standalone fred-agent-evaluator application before upgrading Fred. Follow the existing [application deployment contract](../../platform/FORKING_GUIDE.md); grant the intended teams access through the existing application permissions. Preserve the evaluator service and its database.

## Configuration

No new configuration fields are introduced. Existing application registration and ingress/proxy settings must expose the evaluator UI and API. Deployments already using the evaluator through Apps need no further configuration. Deployments not using evaluations can upgrade normally.

## Upgrade

Only after the authorization prerequisite is verified, validate that an authorized team can open the evaluator through Apps, then deploy Fred. The built-in Evaluations settings entry, screens and direct evaluator task polling are removed. Use Apps to inspect evaluation runs and progress; the old settings URL falls back to Members.

Hosted UI consumers using `InlineDrawer` with `resizable` must explicitly use `layout="push"` and provide `width` as a pixel string (for example, `"480px"`, also the default). Relative CSS units remain supported without `resizable`; invalid resize widths are rejected by TypeScript and at runtime.

`TextArea` retains native uncontrolled usage, including `defaultValue`. Controlled `value` requires `onChange`, `readOnly={true}` or `disabled={true}`; do not combine `value` and `defaultValue`. Its counter follows edits and native form reset.

Selectable `DataTable` consumers must supply a stable `rowKey` function, controlled `selectedKeys` set and `onSelectionChange` handler (also when `selectable` is a dynamic boolean). This enforces the existing documented selection requirement in TypeScript. Sortable column labels must be unique across all columns; ambiguous labels are rejected. Controlled sorting requires both `sortState` (including `null`) and `onSortChange`; omit both for internal sorting, with `sortValue` on every sortable column.

ProgressBar consumers must provide `aria-label` or `aria-labelledby`. DataTable consumers should supply stable column `key` values when labels change or duplicate-label column objects are recreated.

Standalone `TablePagination` requires a nonnegative safe-integer page count and a current index inside that count (index zero for an empty result). When filtering reduces the count, update the controlled index together with the count; inconsistent props are rejected explicitly. Its `rowsPerPage` and every `rowsPerPageOptions` value must be positive safe integers, including when the selector is hidden; invalid sizes are rejected before rendering.

Hosted consumers can opt into typed table-row activation, localized drawer action labels and semantic KPI tones after the UI package release. Server pagination counts and offsets must be nonnegative safe integers; page sizes must be positive safe integers.

## Validation

Confirm Apps opens the evaluator for an authorized team. Independently verify that direct API requests from authenticated users without the target team membership or application grant are denied, through both the application gateway and legacy `/evaluation/` path. For a member of a granted team, also verify denial of viewing without `CAN_READ`, creation/cancellation without `CAN_UPDATE_AGENTS`, and real-conversation evaluation without `CAN_READ_CONVERSATIONS`, through both paths; verify permitted operations succeed for appropriately authorized users. An Apps admission check alone is insufficient; failed or missing API authorization blocks rollout. Verify Members and Activity still work and Fred no longer calls `/evaluation/v1` directly. The shared UI package must pass archive/consumer validation; StatusBadge and other reusable exports remain available.

In the evaluation application, activate a run row with Enter, close the case drawer using its localized close action, and inspect outcome KPI values in both themes. Open the agent selector in a scrolled hosted form and navigate its options: only the options list should scroll, while the form and Fred host retain their position.

## Rollback

Restore the previous Fred frontend image to recover the built-in screens. Keep the evaluator service, application registration and data; this change introduces no data migration or deletion.

## Limitations

Publishing the alpha.3 npm package is a separate operation. Rebuild the candidate archive and regenerate release evidence before publication; evaluator registry pins remain pending that release. The removal does not publish packages, deploy the external evaluator, change evaluation permissions or delete historical evaluations.

`InlineDrawer floating` requires explicit `layout="push"`; the unsupported overlay combination now throws instead of rendering a transparent modal panel.

Activatable `DataTable` rows require at least one column. Their action labels include row identity independently of cell content; use `labels.activateRow(key)` for localized human-readable names.
