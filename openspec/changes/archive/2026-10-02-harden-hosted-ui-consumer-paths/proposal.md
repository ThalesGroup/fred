## Why

The first review round on the replacement PR, a re-triage of the 82 comments from the
closed PR and two fresh-context reviews found hosted-consumer paths the evaluator
reaches (form file retry, unnamed progress and selectors, unlocalized landmark,
error association) and public props the type system can close. Tracks #2887.

## What Changes

- Row activation is pointer-only; keyboard users use the in-row control.
- Public TextArea is controlled and owns its id; controlled sorting is a typed pair;
  DataTableLabels is pagination-only; the toast copy action is FRED-internal.
- ProgressBar can be named and announces its bounded percentage; the rows-per-page
  selector is named; Breadcrumb accepts a landmark label; FileDropzone clears its
  input after a pick and ties its error to the control.
- PageEmptyState's action and the overlay drawer width get static defaults.

## Impact

Canonical shared components, `libs/frontend/ui/src/index.tsx`, package fixtures and
smoke, README. fred-agent-evaluator drops `copyLabel` and its selection labels.
