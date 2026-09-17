## Why

`ppt_builder` can only fill zones a designer already drew. On a template that holds them it works well; on a plain one it has nowhere to write. A template reduced to a title layout, a blank content layout and a closing slide produced a thirteen-slide deck with nine title slides (session `0fc6bbd8`): the blank layout carries no placeholder, so the analysis excludes it (`no_placeholder`), the blank example slide has no zone so it is offered as `fixed` and ignores whatever content it is given, and every intent the agent asked for — `content`, `cards`, `statement`, `section` — degraded onto the cover, the only pattern left with a text zone.

That is the documented behaviour working as designed, and the design is the limit: the people this capability is for do not have the skill to build a rich template, and a tool that only fills existing slides makes every deck of a given template look alike.

## What Changes

- **A design system is extracted from the template**, alongside the pattern inventory: theme palette, type scale, the master's usable area and margins. The analysis already reads theme fonts to measure text; this widens it to what composing needs.
- **Composed patterns.** The renderer gains a second strategy: laying out text boxes of its own on a blank layout, drawn with the template's own tokens. A first set covers what the intents ask for and the template often lacks — a statement, a two-column split, a card row, a big figure, an agenda.
- **Composition is a fallback, never a preference.** The pattern scoring added in `ppt-builder-capability` already states, per slide, how much of the given content a template pattern can show. A composed slide is used only when no included pattern can carry the content; a template that holds the slide always wins.
- **The plan can ask for emphasis.** Slide and item content gains optional formatting — a level of emphasis, an accent — resolved against the template's palette and type scale. The agent cannot name a colour or a size, only a role.
- **BREAKING (stated property, not an API).** `ppt-builder-capability` says the renderer never adds free shapes: "Nothing is ever drawn: the corporate design cannot be broken." That becomes: nothing is drawn outside the template's own design tokens. The guarantee changes from "we never draw" to "what we draw cannot leave the charter".
- `PatternSource` gains a third value alongside `layout` and `slide`. It is persisted in agent configs; the addition is backward compatible and inventories saved before it keep loading.
- **Author review covers composed patterns**: they appear in the config widget like any other, can be relabelled, re-intented or excluded, so an author who wants only their own slides can switch them off.

## Capabilities

### New Capabilities

- none — this extends the capability `ppt-builder-capability` introduces.

### Modified Capabilities

- `ppt-builder`: the renderer may compose a slide from the template's design tokens when no pattern of the template can carry the content; the "never adds a shape" requirement is replaced by "never draws outside the template's tokens"; the plan gains optional emphasis; the inventory gains a design system and composed patterns.

## Impact

- `libs/fred-capability-ppt-filler/fred_capability_ppt_filler/builder/`: `analysis.py` (design-system extraction), a new `compose.py` (composed patterns and their layout), `models.py` (`PatternSource`, design system, emphasis), `plan.py` (emphasis fields, the fallback rule on top of `score_pattern`), `render.py` (drawing strategy, invariant docstring), `tools.py` (catalogue wording for composed patterns).
- `apps/frontend/src/rework/features/capabilities/ppt_builder/`: the review widget must render a composed pattern that has no source slide to thumbnail.
- Stored agent configs: additive only; `analysis.ANALYSIS_VERSION` is bumped so existing agents recompute on their next save through the mechanism already in place.
- Tracking: GitHub issue #2679.
