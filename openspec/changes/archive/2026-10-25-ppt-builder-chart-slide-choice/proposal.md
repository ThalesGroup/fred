## Why

Live (session 693bd457, the owner's own template): three chart example slides, one with a centred chart under the title, two with a text box beside the chart (left and right). Eleven chart-only slides (a takeaway, which goes to the speaker notes, no bullets) were rotated across the three, so two slides in three showed an empty text box. The assignment's variety prices (`_REUSE` 8 per earlier use, `_REPEAT` 3, `_OVER_MAX` 100 with `variety_max_uses` 1) outweigh the 1.5 an unfilled zone costs. Related follow-up of the chart work, GitHub issue #3136.

Owner principle (2026-10-16): pick the template slide that leaves the fewest unfilled zones; fewer empty zones beats variety.

## What Changes

- **Variety only chooses between equally filled slides.** A fitting template slide is dropped from a slide's candidates when another of the same kind leaves fewer zones unfilled (text zones swept away, empty pictures) at no higher fit cost. Reuse, repeat and max-uses prices then arbitrate only between the remaining ones. All kinds.
- **The variety ask never offers a dropped variant**: one that would leave a zone unfilled on every slide of the group is not a variant to recast to.
- **A chart without a requested kind tries chart slides first**, before a content area (a separate tier, as when `chart` is asked): variety never moves a chart into a content area while a chart slide holds it.
- The design pin (`built_on`) and `like` are unchanged: a slide built earlier on a now-dropped variant keeps it.
- Amends `ppt-builder-charts` D10's assumption that the 1.5-point empty-takeaway cost lets the wide chart slide win.

## Capabilities

### New Capabilities

- none

### Modified Capabilities

- `ppt-builder`: adds requirement "Variety never leaves a zone unfilled". Extends `ppt-builder-capability` and `ppt-builder-charts` (both in flight): applied and archived after them.

## Impact

- `libs/capabilities/fred-capability-ppt-filler/fred_capability_ppt_filler/builder/assign.py` (`_weigh`, `_check`, `_fullest`, `_kept`, `_tiers`, `_repeats`).
- Tests: `tests/test_chart_slides.py` (regression on three chart slides), `tests/test_assign.py` and `tests/test_build_tool.py` (expectations that relied on variety picking an emptier variant).
- No schema, API, frontend, dependency or analysis change; `ANALYSIS_VERSION` unchanged.
- Migration: covered by the PR's `ppt-builder-capability` note (unreleased capability, no operator action).
- Tracking: #3136 (related follow-up).
