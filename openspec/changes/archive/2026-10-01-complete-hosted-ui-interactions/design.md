## Context

See proposal.md. Canonical components generate SDK implementation and declarations; edit those inputs, never generated copies. Existing props remain source compatible.

## Goals / Non-Goals

Complete the three developer-approved consumer contracts. Do not publish, change registry versions, alter backend behavior or introduce a second component implementation.

## Decisions

DataTable gets optional onRowClick(row), preserving row type. Row background/cells activate it while embedded buttons, links, inputs, labels, selects and textareas retain their own actions. Callback takes precedence over background selection when both are supplied; checkboxes retain selection. Interactive rows accept Enter/Space only when the row itself has focus. No callback preserves current selection behavior.

InlineDrawer gets optional closeLabel, defaulting to the existing English label; the evaluator supplies its translated label.

KpiStatCard gets optional tone using StatusBadgeTone, defaulting to neutral. Semantic design tokens color the value; labels/counts still convey the outcome without relying on color. Existing callers remain neutral.

## Risks / Trade-offs

Embedded actions could double-activate → test callback isolation and selection alongside keyboard behavior. Packed declarations could drift → rebuild the archive and typecheck/test the actual evaluator consumer. Publication evidence is invalidated by changed archive bytes and must be regenerated before release.
