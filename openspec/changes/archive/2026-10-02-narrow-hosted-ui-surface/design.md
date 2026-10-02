## Context

Narrowing happens at the package boundary with type-only aliases over canonical
components, as the package already does for `Button`. No runtime wrapper.

## Decisions

- `rowKey` stays optional: the evaluator renders a static case list without a
  stable identity, as do several FRED pages.
- Selection labels stay in `DataTableLabels` because the evaluator's label factory
  returns that type; they are inert without selection.
- Overlay accessibility (modal semantics, focus containment) matches FRED's in-app
  drawer. Improving it is a FRED-wide change, out of this slice.

## Deferred

Any additional prop is opened when a hosted application needs it, with its use case.
