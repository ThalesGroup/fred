## Why

`ppt_builder` can only fill zones a designer already drew. On a template that holds them it works well; on a plain one it has nowhere to write. A template reduced to a title layout, a blank content layout and a closing slide produced a thirteen-slide deck with nine title slides (session `0fc6bbd8`): the blank layout carries no placeholder, so the analysis excludes it (`no_placeholder`), the blank example slide has no zone so it is offered as `fixed` and ignores whatever content it is given, and every intent the agent asked for — `content`, `cards`, `statement`, `section` — degraded onto the cover, the only pattern left with a text zone.

That is the documented behaviour working as designed, and the design is the limit: the people this capability is for do not have the skill to build a rich template, and a tool that only fills existing slides makes every deck of a given template look alike.

There is a second limit, visible even on a rich template: what comes out is bullet lists in columns, whatever the content was. Not because the model cannot do better — the inventory already speaks of `cards`, `steps`, `statement`, `comparison`, and `PlanItem` is described in the code as a KPI card — but because nothing ever asks *what shape this content has*. `score_pattern` rewards showing the most fields; four bullets and four cards show the same fields, so nothing prefers the cards. And `SlidePlan.bullets` is the easiest field in the schema to fill, so it is the one that gets filled.

## What Changes

The capability stops being a form-filler that happens to draw, and becomes **a designer that happens to emit PowerPoint**. Two layers, in this order, with a hard boundary between them.

### 1. The design layer — reason in design terms, never in PowerPoint terms

- **The template is read as a design system, not as a pile of slides.** Besides the pattern inventory, the analysis extracts the tokens a designer would name: colours as **surface/text pairs** rather than loose values, with their contrast checked; the type scale per text level; a spacing scale and the vertical rhythm it implies; the grid, derived from the slide's real dimensions; the shape language (corner radius, strokes); and the **optical anchors** the template aligns to.
- **Content is classified by shape before any slide is chosen.** Parallel short items, an item carrying a figure, two opposed sets, an ordered sequence, a single sentence, a quantity out of a whole, continuous prose — each is a different *content shape*, and each has a natural expression. This classification is made by the renderer, not merely suggested to the agent, so a weaker model cannot collapse everything back onto bullets.
- **A component library replaces the list of ad hoc layouts.** Card, Chip, Stat, Bar, Divider, Image frame — small, composable pieces with typed slots, exactly as a UI library has them. Above them, compositions that arrange those pieces: card row, stat band, comparison, steps, statement, agenda, figure-and-caption.
- **Every component declares a capacity and a set of fixed variants.** PowerPoint has no auto-layout: nothing reflows, nothing pushes a neighbour. So a card row is not fluid — it is a 2-up, a 3-up or a 4-up, chosen by item count and measured text, and it states plainly how much it can carry.
- **Hierarchy is carried by the components, not asked for.** A figure is large because it sits in a Stat, not because the plan requested a size. One accented element per slide — if everything is emphasised, nothing is. Letting the plan ask for emphasis of its own is deliberately left to a follow-up change.
- **The deck is consistent slide to slide, not only inside a slide.** Every composition aligns to the template's optical anchors, so a title does not shift between slides — the most recognisable mark of a deck nobody designed.
- **Density has a ceiling.** When one planned slide carries more than any variant can hold, it splits into a continuation slide rather than being crammed or cut.

### 2. The translation layer — turn the resolved design into PowerPoint

- **One place, and only one, knows about PowerPoint.** It receives a resolved composition — components, variants, boxes on the grid, token references — and emits shapes: the template's placeholders where the template has them, autoshapes and text boxes where it does not, at absolute coordinates.
- **The boundary is enforced, not merely intended.** No PowerPoint concept (placeholder, EMU, shape type, layout index) appears above this layer; no design freedom appears below it. A colour, typeface or size that is not a token cannot reach a shape.
- **Tokens are referenced, not copied.** A composed shape points at the theme's colour slot and font reference rather than carrying the value read from it, so a deck follows a later theme change instead of quietly falling out of charter. The analysis already reads those references; only the drawing side still writes literals.
- **Components are real, editable shapes**, never a picture of a slide. A deck stays a deck its reader can open and edit — with text alternatives, decorative markings and a reading order that follows the composition.
- **Charts stay out; drawing does not.** A progress bar is two rounded rectangles, a bar row is a rectangle per value — primitives, on-charter, editable. A real chart object with axes, legend and data table remains out of scope, as in `ppt-builder-capability`.

### Consequences

- **Composition is a fallback, never a preference.** A slide is composed only when no included pattern of the template can carry the content's shape; a template that holds the slide always wins.
- **BREAKING (stated property, not an API).** `ppt-builder-capability` says the renderer never adds free shapes: "Nothing is ever drawn: the corporate design cannot be broken." That becomes: nothing is drawn outside the template's own design tokens. The guarantee changes from procedural ("we never draw") to material ("what we draw cannot leave the charter").
- `PatternSource` gains a third value alongside `layout` and `slide`. It is persisted in agent configs; the addition is backward compatible and inventories saved before it keep loading.
- **Author review covers composed patterns**: they appear in the config widget like any other, can be relabelled, re-intented or excluded, and one agent-level switch turns composition off entirely for an author who wants only their own slides.

## Capabilities

### New Capabilities

- none — this extends the capability `ppt-builder-capability` introduces.

### Modified Capabilities

- `ppt-builder`: the template is read as a design system; content is classified by shape and expressed through a component library with declared capacities; the renderer may compose from the template's tokens when no pattern of the template can carry the content; the "never adds a shape" requirement is replaced by "never draws outside the template's tokens".

## Impact

- `libs/capabilities/fred-capability-ppt-filler/fred_capability_ppt_filler/builder/`: `analysis.py` (design-system extraction), a new `design_system.py` (tokens and the grid), a new `components.py` (the library, its variants and capacities — design layer, no python-pptx import), a new `compose.py` (content-shape classification and composition resolution), `models.py` (`PatternSource`, design system), `plan.py` (the fallback rule on `_shown_fields`), `render.py` (the translation layer and the restated invariant), `tools.py` (catalogue wording for composed patterns).
- `apps/frontend/src/rework/features/capabilities/ppt_builder/`: the review widget must render a composed pattern that has no source slide to thumbnail.
- Stored agent configs: additive only; `analysis.ANALYSIS_VERSION` is bumped so existing agents recompute on their next save through the mechanism already in place.
- Tracking: GitHub issue #2679.
