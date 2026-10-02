## Decisions

- Reachable paths get minimal runtime changes; unreachable ones are closed by types
  or static defaults (type="button", max-width) per the review disposition rule.
- Row keyboard activation is removed rather than given a role: a `role="button"` row
  would nest interactive controls, and the consumer already renders an in-row button.
- PageEmptyState keeps application icons in FRED (configurable agent icon); the
  package build keeps narrowing it to Material Symbols.
