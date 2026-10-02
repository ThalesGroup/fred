## Why

The light theme reads heavy and greyish, and switching between light and dark looks broken (#2915). The surface scale is asymmetric: in light, `surface-main` sits at tone 98 and most `surface-container-*` levels are darker than it; in dark, `surface-main` sits at tone 6 and the containers are lighter. The same token recedes in one theme and floats in the other. The neutral ramp also carries a visible lavender cast that dulls the light theme.

## What Changes

- Regenerate the `--core-cold-grey-*` neutral ramp with a discreet blue tint (CIE LCh chroma 1.5, hue 280°) at the same tone steps, plus the two half steps the new scale needs (97.5, 94.5). Every token built on this ramp (surfaces, text, outlines) shifts hue, not lightness.
- Apply one surface rule to both themes: **each `surface-container-*` level sits further from `surface-main` than the level below it** (lighter in dark, darker in light).

  | Token | Light | Dark |
  |---|---|---|
  | `surface-main` | 100 | 6 |
  | `surface-container-lowest` | 99 | 8 |
  | `surface-container-low` | 97.5 | 10 |
  | `surface-container` | 96 | 12 |
  | `surface-container-high` | 94.5 | 15 |
  | `surface-container-highest` | 93 | 18 |

- Add `--surface-floating` (light 100, dark 15) for elements that float above the page: menus, popovers, tooltips, modals, editor popups. It is the one named exception to the scale.
- Remap the usages of `surface-container-lowest` and `surface-container-highest` whose visual role flips under the new scale (filled fields, code wells, page backgrounds, floating elements, the main nav). Usages of `surface-container-low`, `surface-container` and `surface-container-high` keep their token; only their tone changes.

Non-goals (follow-up changes): secondary text tones, outline levels, `secondary-container` vs `primary-container`, dead and undefined tokens.

## Capabilities

### New Capabilities

- `frontend-surface-scale`: the neutral surface tokens of the Fred frontend and the rule that relates them to the page background in both themes.

### Modified Capabilities

None.

## Impact

- `apps/frontend/src/styles/color-ramps.css`, `colors-semantic-light.css`, `colors-semantic-dark.css`.
- About 60 CSS/SCSS/TSX usages of `surface-container-lowest` / `-highest` under `apps/frontend/src/rework/`, plus `apps/frontend/src/styles.css` (body background).
- Visual change only: no API, contract, or data change. Borders currently drawn with `surface-container-highest` (DataTable, TablePagination) become visible grey lines in light; that is accepted here and revisited with the outline follow-up.
- Docs: `docs/swift/platform/FRONTEND_CODING_GUIDELINES.md` (surface token section), `docs/swift/ux/COMPONENT-UX.md` (surface row).
- Migration note required (patch: no operator action).
