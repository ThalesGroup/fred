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

Hosted UI consumers using `InlineDrawer` with `resizable` must explicitly use `layout="push"` and provide `width` as a pixel string (for example, `"480px"`, also the default). Relative CSS units remain supported without `resizable`; invalid resize widths are rejected by TypeScript and at runtime.

`TextArea` retains native uncontrolled usage, including `defaultValue`. Controlled `value` requires `onChange`, `readOnly={true}` or `disabled={true}`; do not combine `value` and `defaultValue`. Its counter follows edits and native form reset.

Selectable `DataTable` consumers must supply a stable `rowKey` function, controlled `selectedKeys` set and `onSelectionChange` handler (also when `selectable` is a dynamic boolean). This enforces the existing documented selection requirement in TypeScript. Sortable column labels must be unique across all columns; ambiguous labels are rejected. Controlled sorting requires both `sortState` (including `null`) and `onSortChange`; omit both for internal sorting, with `sortValue` on every sortable column.

## Validation

Confirm Apps opens the evaluator for an authorized team, while unauthorized teams retain the existing admission restrictions. Verify Members and Activity still work and Fred no longer calls `/evaluation/v1` directly. The shared UI package must pass archive/consumer validation; StatusBadge and other reusable exports remain available.

## Rollback

Restore the previous Fred frontend image to recover the built-in screens. Keep the evaluator service, application registration and data; this change introduces no data migration or deletion.

## Limitations

Publishing the alpha.3 npm package is a separate operation. The removal does not publish packages, deploy the external evaluator, change evaluation permissions or delete historical evaluations.
