## 1. Sequencing

- [ ] 1.1 Close and archive `ppt-builder-capability` (its task 7.1, the end-to-end pass, is what the September sessions exercised) so `openspec/specs/ppt-builder/spec.md` exists — verify: `openspec archive ppt-builder-capability` succeeds and `openspec validate ppt-builder-composition --strict` no longer reports that the target spec is missing

## 2. The design system

- [x] 2.1 Read the template's tokens into a `DesignSystem`: colour PAIRS (surface + the text colour that belongs on it), type scale per text level with size, weight and line height, a spacing scale and its vertical rhythm, the grid derived from the usable area and the slide's real dimensions, and the shape language (corner radius, strokes) — verify: unit tests on the reference template and on a stripped one assert each of those, that a template misusing its theme slots still yields a text colour the master actually uses, and that a non-16:9 template yields a grid from its own dimensions
- [x] 2.2 Measure each pair's contrast and fall back to the template's own ink or background when it fails; refuse to offer a surface whose pair cannot pass, and never invent a colour — verify: a template with a low-contrast accent yields a usable pair or no fill, and no RGB absent from the template appears
- [x] 2.3 Read the optical anchors (title ordinate, content-block ordinate, footer band) from the master and from the template's own slides, preferring the slides when they disagree — verify: both templates yield anchors, and a template whose slides differ from its master keeps its slides' values
- [x] 2.4 Record, per token, whether it has a theme reference to point at or could only be read as a literal — verify: a token read off a shape is marked unreferenced
- [x] 2.5 Persist it in `TemplateInventory` and bump `ANALYSIS_VERSION` — verify: an inventory saved without it loads, and a save recomputes it from the stored template (the existing refresh test, extended)
- [x] 2.6 Stop excluding a blank layout for holding no placeholder: it is the canvas — verify: the stripped template's `layout:1` is no longer excluded with `no_placeholder`
- [x] 2.7 Choose as canvas the placeholder-free layout carrying the MOST of the template's own furniture, not the barest, and read `showMasterSp` rather than assuming the master's shapes are inherited (design D17) — verify: given a bare layout and a dressed one the dressed wins; a layout whose furniture crosses the middle of the slide does not; a layout that switches the master off inherits nothing
- [x] 2.8 Measure every inherited fixture and trim it out of the usable area before the grid is built, taking the trim that leaves the most room and treating neither the full-bleed background nor a placeholder as a fixture — verify: a logo bottom right moves the area's lower edge above it and keeps the full width; a full-slide rectangle reserves nothing
- [x] 2.9 Move the optical anchors below a band the canvas inherits, title and content together so their distance stays the template's (design D13) — verify: the same template with and without a top band yields a title ordinate below the band and an unchanged title-to-content gap

- [x] 2.10 Read the component style the template demonstrates — painted or outlined blocks, corner radius, the inset inside a block and the gap between two side by side, and whether a figure sits above or below its label — counting only shapes that actually paint something (design D18) — verify: a template with outlined cards, a wide corner, wide insets, a measurable gap and figures under their labels yields all five; a bare template keeps every default; a row of plain text boxes is not read as an outlining house
- [x] 2.11 Take the grid's gutter from the observed gap when the template shows one — verify: a template whose columns are 0.3in apart yields that gutter rather than a step of the spacing scale

## 3. The component library (design layer)

- [x] 3.1 Create `components.py` with the typed pieces — Card, Chip, Stat, Bar, Divider, Image frame — each declaring its slots, the tokens it consumes and its capacity — verify: each component resolves against both templates' design systems and exposes a capacity; a test asserts the module imports no `pptx` symbol
- [x] 3.2 Add the compositions over those pieces — card row, stat band, comparison, steps, statement, agenda, figure-and-caption — each with a fixed variant set and no fluid resizing — verify: a composition given 2, 3 and 4 items selects the matching variant, and every box of every variant sits on the grid inside the usable area
- [x] 3.3 Declare and honour each component's degenerate cases, starting with the Bar's minimum legible length (a rounded rectangle's radius follows its shorter side, so a value shorter than its thickness distorts) — verify: a Bar at 2% is drawn at its minimum or omitted, never as a shape wider than it is long
- [x] 3.4 Give every component its layout rules: gaps taken from the spacing scale only, one accent per slide (a second dropped and reported), and Image frames that fill-and-crop or contain but never distort — verify: a composition's gaps all map to scale steps; a two-accent slide renders one and reports the other; an image of the wrong ratio is cropped, not stretched
- [x] 3.5 Declare, per component, its text-frame behaviour — internal margins set rather than inherited, vertical anchor, and the chosen auto-fit behaviour — and its shape order, since creation order is z-order — verify: a Card's text frame carries the component's insets rather than the 0.1in default, and a Card is created before the text that sits on it
- [x] 3.6 Declare each composition's density ceiling — verify: every variant states a maximum item count and text per slot, and the ceiling is reachable from the component's capacity
- [x] 3.7 Add `composed` to `PatternSource` and project each composition into a `Pattern` with zones, roles and boxes — verify: the stripped template yields a composed pattern per supported intent, and downstream code (catalogue, scoring, review) treats it like any other pattern with no special case

- [x] 3.8 Honour the observed style in the components: the gap between columns, the air inside a block, and the order of a figure and its label — keeping the figure first in the reading order whichever way it is printed, and keeping "has cards" separate from "are cards painted" (design D18) — verify: the same composition on two templates yields their own gaps, paddings and stat order, and every variant still holds together under values the capability would not have chosen

- [x] 3.9 Give each piece the largest rung of the template's scale its box can carry, judged on width AND height, keeping the slide title at its own size and a heading always above the body under it (design D19) — verify: a narrower card takes a smaller or equal size, never a larger one; the title keeps the scale's title size; no heading shares a rung with the text under it
- [x] 3.10 Size a Card from the rows it stacks rather than from the content band, every card of a row alike (design D20) — verify: a card row leaves the lower part of the band free, and all the cards of one row are the same height


## 3b. The layout language (design D21)

- [x] 3b.1 Add the box model: a node is a leaf that draws or a stack that arranges children in a row or a column, sized `hug` or `fill`, with gap, padding and cross-axis alignment taken from the template's spacing scale — verify: a column hugs its children, a `fill` child takes what is left, two `fill` children share by weight, a row never overlaps, and `None` padding is no padding where `0` is the scale's tightest step
- [x] 3b.2 Resolve a tree to absolute per-mille boxes in two passes, measure bottom-up then arrange top-down, emitting a container before the children drawn on it — verify: a panel of cards of rows resolves three levels deep with every child inside its parent, and a card is placed before its text
- [x] 3b.3 Declare every existing composition as a tree over the box model, keeping `compose()`, `COMPOSITIONS` and the declared capacity unchanged — verify: the whole existing suite passes with the geometry computed by the engine
- [x] 3b.4 Add the nested archetypes the real decks are made of: a framed panel holding a row of cards, and a lead block beside a column of cards — verify: each resolves on both templates, every card sits inside its panel, the panel hugs its cards rather than running to the footer, and both keep the optical anchors
- [x] 3b.5 Compose with the template's OWN icons instead of excluding its icon bank, offering only the ones it names (design D22) — verify: a template carrying a named bank yields those icons and no file names, an icon keeps its own aspect, a named icon is copied onto the composed slide as a real picture, an unnamed frame is removed and an unknown name is reported
- [x] 3b.6 Rich cards: icon, heading, qualifying label and body in one component — verify: every row sits inside its card, the three text rows keep three distinct sizes, and a template without icons still composes the card without one

## 4. Translation to PowerPoint

- [x] 4.1 Render a composed pattern by drawing its resolved boxes on the blank canvas, then filling them through the existing path — verify: a rendered composed slide goes through the same fitting, truncation and reporting as a template pattern (assert on the warnings, not on the drawing)
- [x] 4.2 Write tokens as LIVE references — a theme colour slot for a colour, the major/minor latin reference for a typeface — falling back to a literal only for a token marked unreferenced — verify: a composed slide's XML carries theme references, and changing the theme variant moves the composed slides exactly as it moves the template's own
- [x] 4.3 Fill a placeholder the blank canvas already carries (a title, most often) instead of drawing a box for it — verify: on a canvas holding a title placeholder the composed title uses it and inherits the template's title styling
- [x] 4.4 Align every composition to the optical anchors whatever its variant — verify: across a deck mixing template patterns and several compositions, all titles share one ordinate and all content blocks another
- [x] 4.5 Name every composed shape, and set text alternatives, decorative markings and reading order — verify: shapes are findable by name; Card backgrounds and Dividers are decorative, Image frames carry alt text, and reading order follows the composition rather than creation order
- [x] 4.6 Make the layer boundary structural: the design-layer modules import no `python-pptx`, and `render.py` resolves no colour, typeface, size or position of its own — verify: an import test fails if a design-layer module imports `pptx`, and a test walks a composed slide's XML and fails on any value absent from the palette and type scale
- [x] 4.7 Keep every composed shape a real editable shape, never a picture — verify: a composed slide's shapes are autoshapes and text frames, and its text is readable from the XML
- [x] 4.11 Resize each Card to the text it actually holds once filled, the row taking the tallest (design D20) — verify: the same composition with short and with long text yields different card heights, and the cards of one row stay equal
- [x] 4.12 Derive the muted surface as a tint of the template's ink written as lumMod/lumOff, never off a theme slot by name (design D12b) — verify: a template with a vivid `lt2` still fills its cards with a quiet tint, and the slide holds no literal colour
- [x] 4.10 Draw a Card painted or outlined as the template draws its own, keeping Bars, Chips and Dividers painted either way, and write the outline as a theme reference like every other colour — verify: on an outlining template the composed cards carry no fill and a line, the progress bars are still painted, and the slide still holds no literal colour
- [x] 4.9 Report a composed shape that overlaps a fixture the canvas inherits — verify: a normal composed slide reports nothing, and a shape placed over a reserved fixture is named in the result
- [x] 4.8 Restate the invariant in `render.py`'s docstring and in the archived change's compact doc wherever it claims the renderer never draws — verify: no doc still claims the renderer never draws

## 5. Choosing how content is expressed

- [x] 5.1 Classify a slide's content by shape in the renderer — parallel short items, item with a figure, two opposed sets, ordered sequence, single sentence, quantity out of a whole, continuous prose — verify: each shape maps to its composition on a table of cases, and prose is never broken into cards
- [x] 5.2 Apply the classification even when the plan asked only for body bullets, while honouring an intent the agent did ask for when the content supports it — verify: a four-short-item slide planned as bullets renders as a card row; a genuine bullet list still renders as one
- [x] 5.3 Compose structured content outright, whatever the template already draws for it, and keep verbatim reuse for a plan that names a pattern id (design D5, amended) — verify: on the reference template a slide of ordered steps is composed even though the template has its own steps pattern, and naming that pattern renders it unchanged
- [x] 5.3c Honour an intent the content cannot express — agenda, figure-and-caption, two columns — and move the content into the fields that intent reads (design D9) — verify: a slide asking for an agenda renders an agenda with its bullets carried into items, while a slide asking for cards is still decided by its content
- [x] 5.3b Decide the remaining cases — prose and single sentences — on `shown_fields`' share and NOT on `score_pattern`'s composite ranking — verify: a genuine paragraph still lands on the template's own text pattern, and a preferred-but-lossy pattern does not suppress composition
- [ ] 5.4 Split a planned slide that exceeds every variant into ONE continuation slide carrying the same title, and fit-and-report anything beyond that — verify: an overfull slide becomes two with the split named in the result; a slide carrying many times the capacity yields one continuation and a reported remainder
- [ ] 5.5 Report composed slides in the tool result, and state a deck whose length differs from the plan — verify: the result names the composed slides and any split, and the deck itself carries no mark
- [ ] 5.6 Add the agent config field "use only the slides of my template" and honour it — verify: with it set, the stripped template composes nothing and reports the lost content as today; the setting survives a re-analysis

## 6. Review surface

- [ ] 6.1 Render composed patterns into the patterns deck the review widget previews — verify: the widget shows a thumbnail for a composed pattern with no source slide, through the existing code path
- [ ] 6.2 Surface the agent-level switch in the config widget — verify: toggling it in the form round-trips through save and reload

## 7. Verification

- [ ] 7.1 Visual pass: build a deck on the stripped template and on the reference one, convert and read every slide — verify: the stripped deck is varied and on-charter, no slide repeats the same bullet-list shape, titles and content blocks hold their ordinate across the deck, the furniture each layout carries (logo, band, footer) is visible and never drawn over, and the reference deck reads as the template's own work
- [ ] 7.2 Theme-change pass: open a composed deck, switch the theme's colour variant and fonts, and read it again — verify: the composed slides follow the change exactly as the template's own slides do
- [ ] 7.3 `make code-quality` and `make test` green in `libs/capabilities/fred-capability-ppt-filler`; `fred-performance-reviewer` on the analysis path (composition runs at save and at render)
- [ ] 7.4 `/code-review` on the branch diff; apply fixes
- [ ] 7.5 Update `docs/swift/capabilities/AUTHORING.md` only if the capability authoring surface changed — verify: reread it against the diff and state the outcome either way
