## 1. Surface

- [x] 1.1 Remove `TablePagination` and direct `Toast` exports and their types
- [x] 1.2 Narrow public `DataTableProps` (no selection) and `InlineDrawerProps` (single overlay)
- [x] 1.3 Exclude `type`, `children` and `dangerouslySetInnerHTML` from `SwitchProps`
- [x] 1.4 Internal Dialog, drawer and pagination buttons use `type="button"`

## 2. Evidence

- [x] 2.1 Update validators, isolated consumer fixtures, type-negative cases and browser smoke
- [x] 2.2 fred-agent-evaluator type-checks against the built package with zero errors
- [x] 2.3 FRED frontend `tsc` and shared component/hook tests pass
