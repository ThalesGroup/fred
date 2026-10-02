## Why

The alpha.3 hosted UI surface exposed more than its consumer uses. Every exported
prop became a public contract, and review kept finding edge cases in paths no hosted
application reaches (standalone pagination, direct toasts, row selection, push and
resizable drawers, nested drawer stacks). Hardening those paths added code without
serving fred-agent-evaluator. Tracks #2887.

## What Changes

- Stop exporting `TablePagination` and the direct `Toast`; `ToastProvider`/`useToast`
  and DataTable's built-in pagination remain.
- Narrow public `DataTableProps<T>`: no row selection.
- Narrow public `InlineDrawerProps` to a single overlay: `open`, `onClose`, `title`,
  `closeLabel`, `width`, `headerActions`, children.
- Keep FRED-internal behavior as it was before the review loop; no runtime
  validation, nested-drawer stacking or focus-trap machinery.
- Rule: a prop becomes public when a hosted application uses it.

## Impact

- `libs/frontend/ui/src/index.tsx`, fixtures, validators, browser smoke, README.
- fred-agent-evaluator (`53-evaluation-ui-alpha3`) type-checks unchanged.
