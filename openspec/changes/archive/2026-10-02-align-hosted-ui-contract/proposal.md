## Why

A pre-PR review found the capability spec out of step with the narrowed surface:
it still listed `TablePagination` and `Toast` as exports, described StatusBadge
with paired foreground/background tokens, and stated a surface rule broad enough
to cover every optional presentational prop. Tracks #2887.

## What Changes

- Drop `TablePagination` and `Toast` from the export list.
- Describe StatusBadge as an outlined badge in its semantic tone color.
- Scope the surface rule to components and behavioral variants.
- Record the overlay drawer's current focus behavior as a documented limitation.
- Held Enter/Space no longer re-activates a DataTable row on auto-repeat.

## Impact

Spec and `libs/frontend/ui/README.md` only, plus one guard in `DataTable`.
