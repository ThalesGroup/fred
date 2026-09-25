## Context

See proposal.md — Why. The relevant state: the analysis produces a `TemplateInventory` of patterns, each a layout or an example slide with typed zones; `plan.score_pattern` ranks patterns for a slide, built on `_shown_fields`, which measures the share of the slide's content a pattern can show weighted by what losing each field costs; the renderer instantiates or duplicates and fills, and its module docstring states that nothing is ever drawn. The theme's latin typefaces are already read, to measure text (`text_metrics`).

Two things in the existing code are further along than they look, and this change builds on both rather than beside them. The vocabulary is already design vocabulary: `ZoneRole` is a type scale (`title`, `subtitle`, `heading`, `body`, `caption`, `number`, `label`), `Intent` already names components (`cards`, `steps`, `statement`, `comparison`), and `PlanItem` — `number` + `heading` + `text` — is described in its own docstring as a KPI card. And the drawing primitives exist: `theme._card()` is a rounded rectangle with a solid fill and no stroke, `theme._textbox()` takes size, weight, colour and alignment. What they lack is tokens: they hold literal values because the built-in theme is the only thing that uses them.

Constraint that shapes everything below: the output is a `.pptx` people open and edit. Whatever is composed has to be real, editable PowerPoint shapes — not a picture of a slide.

## Goals / Non-Goals

**Goals:**

- The capability reasons as a designer would — tokens, components, hierarchy, composition — and only then emits PowerPoint.
- A plain template (title layout, blank layout, closing slide) produces a varied, on-charter deck.
- A rich corporate template produces exactly what it produces today.
- Content is expressed according to its shape, so a deck stops being bullet lists in columns.
- Everything composed is traceable to a token read from the template.

**Non-Goals:**

- Free-form design. The agent never chooses a colour, a typeface, a size or a coordinate.
- A layout engine. Variants are fixed and few (see D6).
- Replacing the pattern inventory. Composition is the fallback, not the default.
- A second authoring format (see D4).
- PowerPoint chart objects, tables and SmartArt: still out of scope, as in `ppt-builder-capability`. Drawing a Bar from primitives is not a chart (see D10).

## Decisions

### D1. Sequencing: archive `ppt-builder-capability` first

This change's delta carries MODIFIED requirements, and `openspec archive` refuses that while the target spec does not exist. `ppt-builder-capability` has one open task (7.1, the end-to-end pass on the local stack, which the September sessions have exercised). It is archived first, folding its delta into `openspec/specs/ppt-builder/spec.md`; this change then modifies a real spec. Alternative — making every delta here ADDED — was rejected: it would leave two contradictory statements of the same requirement, one saying the renderer never adds a shape.

### D2. The design system is part of the inventory, not a second artifact

The tokens are persisted inside `TemplateInventory`, beside `patterns`. Alternative considered: a separate stored asset. Rejected — the inventory is already the one thing a save recomputes and a version bump refreshes (`ANALYSIS_VERSION`), and splitting would give two things to keep in step for no gain.

What counts as a token, and why each is needed:

- **Colour pairs**, never loose colours (D11). A surface and the text colour that goes on it.
- **Type scale** per text level, bound to `ZoneRole`, each level carrying size, weight and line height.
- **Spacing scale** — a small set of steps, not one unit — and the vertical rhythm derived from the type scale's line heights. One unit gives consistent gaps only by accident; a scale makes "tight" and "loose" nameable.
- **Grid**, derived from the master's usable area and the slide's *real* dimensions. Nothing assumes 16:9.
- **Shape language**: corner radius, whether the template strokes its shapes or relies on fills.
- **Optical anchors** (D13): the ordinates at which titles and content blocks start, read from the master and from the template's own slides.

### D3. Composed patterns are patterns

`PatternSource` gains `composed`. A composed pattern carries zones with roles and boxes like any other, so the renderer's filling, fitting, truncation and reporting all apply unchanged, and the author review surface, the catalogue and the scoring need no special case. What differs is only creation: instead of instantiating a layout or duplicating a slide, the renderer draws the zones onto the blank canvas first.

This is already proven in the codebase: `theme.default_theme()` draws agenda, cards, steps, statement and contact slides, then runs them through `analyze_presentation`, so the built-in theme's composed slides are already ordinary patterns downstream. This change generalises that from hardcoded values to the template's tokens.

Alternative considered: a separate "composition" path parallel to the pattern path. Rejected — it would duplicate the fitting and reporting machinery this capability spent its whole first change getting right.

### D4. One tool, not several

Composition stays behind the existing `build_presentation` tool. A capability may expose several tools, and this one already does (`list_images_in_folder`), but splitting the build — "compose a slide" beside "build the deck" — would reintroduce the failure the September sessions showed: a small model splitting one deck across several calls and delivering several truncated decks. One call, one deck, remains the rule.

Revisit if the layout vocabulary grows past what one legible schema can carry. A read-only tool exposing the design system (what the template can and cannot do) is a cheaper first step than splitting the build, and would follow the shape of `list_images_in_folder`.

### D5. Composing is the normal path; the template is a language, not a stock

*Amended after the first implementation pass.* As first written, this decision put the template's own pattern first in line and composed only as a fallback, when nothing the designer drew could carry the content without losing some of it. That is the wrong default.

A template is the design **language** a deck is written in — its colour pairs, its type scale, its grid, its fixtures, and the component style its own slides demonstrate. It is not a stock of slides to recycle. A slide should be built for the content it actually carries, drawing as much as possible on what the template shows about how this house draws a card, a figure or a step; it should not be fitted into the nearest thing the designer once drew for another purpose.

So structured content — parallel items, figures, quantities, sequences, opposed sets — is composed. Reusing one of the template's own patterns exactly as it stands is the answer to an explicit request to fill *that* slide, and naming a pattern id in the plan is exactly that request: `named_explicitly` already honours it and stays the one way back to verbatim reuse. That is also the boundary between this capability and `ppt_filler`, whose job is filling a slide that already exists.

Prose is the exception and keeps the loss comparison below: a paragraph belongs in the template's own text pattern, and breaking it into cards reads worse than the list it replaced (D9).

**The loss comparison, for the cases that still use it.** A slide is composed when the best included pattern would lose content. That question is answered by `shown_fields` — the weighted share of the slide's content a pattern can show — and not by `score_pattern`.

`score_pattern` is a *ranking* function: it adds a preference bonus for an author-preferred pattern, subtracts a penalty per empty image zone, and subtracts an overflow penalty, then is only ever consumed through `max(...)`. It is never compared against a threshold, and it cannot be: a score of 94 may mean full coverage with slight overflow, or partial coverage rescued by the preference bonus. Thresholding it would silently suppress composition on exactly the templates that need it — the ones whose author marked a pattern preferred.

So `_shown_fields` becomes the basis of the decision and stops being private. `score_pattern` keeps its job unchanged: choosing between candidates once the decision to use a template pattern has been taken. Two questions, two functions, neither doing the other's work.

### D6. Components, variants and capacity — a grid resolved at build time

The library is small and typed: Card, Chip, Stat, Bar, Divider, Image frame as pieces; card row, stat band, comparison, steps, statement, agenda and figure-and-caption as compositions over them.

PowerPoint has no auto-layout. Every shape is at absolute coordinates, nothing reflows, and a box whose text overflows does not push its neighbour — it overlaps it. A component therefore cannot be fluid. Each composition offers a fixed set of variants (2-up, 3-up, 4-up) and declares a capacity — how many items, how much text per slot — and the variant is chosen from the item count and the measured text through `text_metrics`. This is a grid resolved at build time instead of at paint time.

Deliberately a small, fixed set rather than a solver: a handful of well-proportioned compositions beats a general layout engine that occasionally produces something odd, and each can be reviewed visually once and trusted. *(Superseded in part by D21: the compositions stay a reviewed, fixed set, but they are now declared as trees over a box model instead of computed by hand, because nothing flat can express a panel of cards.)*

Every component also states the rules a designer would not have to be told:

- **Vertical rhythm.** Gaps between blocks come from the spacing scale, never from a value computed to make something fit.
- **Accent economy.** At most one accented element per slide, across every component the composition places. If everything stands out, nothing does.
- **Image fitting.** An Image frame fills and crops, or contains, but never distorts. A stretched logo is the classic failure of a composed deck.

And the PowerPoint mechanics each component depends on, which are not free:

- **Text-frame insets.** A text box carries a default internal margin (0.1in) that silently defeats any padding computed above it. Padding is set on the frame, not guessed around it, and the frame's vertical anchor is part of the component.
- **Auto-fit.** Auto-sizing interacts badly with fixed boxes — the capability already met the case of a box growing in height instead of widening. A component states which behaviour it wants rather than inheriting one.
- **Z-order is creation order.** python-pptx appends, so a Card must be created before the text that sits on it. The order is part of the component's definition, not an accident of the code.
- **Named shapes.** Every composed shape is named, so the fill path and the review surface can find it. `theme._textbox()` already accepts a name.

Each component also declares its degenerate cases, because a proportional corner radius makes some of them visible. A Bar is two rounded rectangles, a track and a value; PowerPoint computes a rounded rectangle's radius from the shape's *shorter side*, so the two agree as long as the value's length exceeds its thickness — and below that the value distorts into a blob wider than it is long. The Bar therefore declares a minimum legible length, below which it is drawn at that minimum or omitted.

### D7. The invariant, restated

"Nothing is ever drawn: the corporate design cannot be broken" becomes "nothing is drawn outside the template's own design tokens". The guarantee is no longer procedural (we never draw) but material (what we draw cannot leave the charter). It is enforced where the drawing happens, so a colour or size that is not a token cannot reach a slide.

### D8. Two layers, and the boundary is structural

The design layer (`design_system.py`, `components.py`, `compose.py`) names tokens, components, slots, grid positions and roles. The translation layer (`render.py`) is the only one that emits shapes.

The boundary is made structural rather than intentional: the design-layer modules do not import `python-pptx` at all, and a test asserts it. Without that, "the renderer decides nothing" degrades into a convention that the first awkward case breaks — a coordinate computed in the renderer because it was easier there, and the guarantee of D7 becomes unverifiable.

Alternative considered: one module with a disciplined internal split. Rejected for the same reason the import ban exists — the property is only worth stating if something checks it.

One consequence worth stating, because it is not obvious: when the blank canvas still carries a placeholder the composition needs — a title, most often — the translation layer fills THAT placeholder rather than drawing its own box. The placeholder inherits the template's own title styling, position and behaviour for free, which is strictly better than reproducing them from tokens. Drawing is the fallback for what the canvas does not already offer.

### D9. The shape of the content decides, and the renderer decides it

Classification happens in the renderer, from the plan's content, not from the intent the agent asked for: parallel short items → card row; item carrying a figure → stat band; two opposed sets → comparison; ordered sequence → steps; single sentence → statement; quantity out of a whole → Bar; continuous prose → body text.

One class of intent escapes the classification entirely, and the ask stands for it: nothing in a slide's content distinguishes an **agenda** from a list of parallel items, or a **figure-and-caption** from any other image slide. Asking is then the only way to get one — before this, every summary slide in a deck came out as cards.

Why not leave it to the agent: `SlidePlan` offers `bullets`, `columns` and `items`, and `bullets` is the cheapest field to fill, so it is the one a weaker model fills. The September sessions showed exactly that degradation under a small model. A hint in the tool description helps the strong models and does nothing for the weak ones; a rule in the renderer helps both. The agent's intent is still honoured when it asked for something the content supports — the classification only decides what the agent left unsaid.

Prose is explicitly kept as prose: the failure mode of this rule is breaking a paragraph into cards that carry no parallel meaning, which looks designed and reads worse than the bullet list it replaced.

### D10. Bars are drawn, charts are not

A quantity out of a whole is two rounded rectangles; a series of values is one rectangle per value with a shared scale. These are primitive shapes, they take their colours from the palette, and they stay editable. A PowerPoint chart object — axes, legend, data table, its own data sheet — is a different artifact, and the exclusion `ExclusionReason.chart` that `ppt-builder-capability` introduced stays in force.

The line is drawn on the artifact, not on the appearance: if the reader should be able to edit the *data*, it is a chart and out of scope. If the shape is an illustration of a number the slide already states, it is a component and in scope.

### D11. Tokens are written as live references, not as copied values

A composed shape refers to the theme — `schemeClr accent1` for a colour, the major/minor latin reference for a typeface — rather than carrying the RGB value or the font name the analysis happened to read.

The asymmetry this fixes is already in the code: `analysis.py` reads the theme font references (`+mj-lt` / `+mn-lt`), while `theme.py` writes literals (`RGBColor(0x1F, 0x2A, 0x44)`, `run.font.name = _FONT`). A literal is a copy of a token, not the token: change the theme variant in PowerPoint afterwards and every copied value stays behind, off-charter, while every reference follows.

For a capability whose whole promise is "this cannot leave the charter", that difference is the promise itself. Literals are kept only where the template gives no reference to point at — a colour read off a shape rather than off the theme — and that case is recorded on the token so it can be reported rather than silently shipped.

### D12. Colour is chosen in pairs, and contrast is checked

The palette is stored as pairs: a surface and the text colour that belongs on it. A component that fills a background does not then choose its text colour — it takes the one the pair carries.

Why this is a correctness rule and not a refinement: "every colour comes from the palette" is satisfied by a Card filled with the primary colour carrying body text in the default dark ink. The slide passes the invariant of D7 and is unreadable. Loose colours make that outcome not merely possible but likely, since the component picking the fill and the fill path writing the text are different code.

The contrast of each pair is measured when the design system is extracted. A pair that fails the minimum falls back to the template's own body ink or its background, whichever passes; if neither does, the surface is not offered as a fill and the component renders unfilled. Never invent a colour to fix contrast — the template's palette is the boundary.

### D12b. A muted surface is a tint, never a slot

`surface-muted` was read off the `lt2` theme slot. Slot names lie — the case that proved it put a vivid cyan there, and every composed card came out flashy.

A muted surface is therefore **derived**: a tint of the template's own ink, written as `lumMod`/`lumOff` on the scheme colour. That is how real templates paint a card, it is quiet by construction, and it is still a reference — the deck follows a theme change exactly as a flat scheme colour would. On a dark deck the page is lifted instead, or the card would be lighter than the text on it.

This does not weaken D11: a tint of a referenced slot is a reference, not a copied value.

### D13. The deck is consistent slide to slide, not only inside a slide

D6 puts every box on a grid within one slide. That is not enough: the most recognisable mark of an amateur deck is a title whose baseline moves a few points between slides.

So the design system carries **optical anchors** — the ordinate where a title starts, where the content block starts, where the footer band begins — read from the master and from the template's own slides. Every composition, whatever its variant, aligns to them. A composed slide placed between two template slides lines up with both.

Anchors are read, never chosen: a template whose own slides disagree with its master keeps its slides' convention, because that is what its reader recognises. A cover, a section divider, a contact slide or an excluded pattern says nothing about where CONTENT goes — its title sits in a narrow column by design — so none of them is measured, and a template that shows no content slide falls back to the master rather than inheriting a cover's geometry.

One correction they need, and only one: when the canvas inherits a band where the template's own slides put their title (D17), the whole set moves down by what the band takes, title and content together, so the distance between them stays the template's. A title a few points lower is a smaller loss than a title hidden under the charter.

### D14. Density has a ceiling, and overflow splits rather than truncates

Each composition declares a maximum: item count per variant, and text per slot. When the content of one planned slide exceeds every variant's capacity, the composer emits a **continuation slide** carrying the same title, rather than cramming or cutting.

Why splitting rather than truncating: the purpose of this whole change is that content stops being lost. Refusing to split and fitting the overflow away would reintroduce exactly the loss composition exists to prevent, and it would do it silently on the slides that carry the most.

Why this does not contradict D4: "one call, one deck" is about the tool call, not the slide count. The deck already may differ in length from what the agent planned, and `ppt-builder-capability` already reports that.

Bounded on purpose: **at most one continuation per planned slide** in this increment. A plan whose single slide carries ten times a variant's capacity is a planning failure, and answering it with a cascade of slides would hide that instead of reporting it. Past the continuation, the remainder is fitted and reported as today. The continuation repeats the title unchanged — no "(2/2)" marker, which is a document convention, not a design one.

### D15. Accessibility is part of the design, not a later pass

Composed shapes carry what a reader using assistive technology needs: text alternatives on Image frames, decorative shapes (a Card's background, a Divider) marked as decorative so they are skipped, and a reading order that follows the composition's own order rather than the order shapes happened to be created in.

PowerPoint carries all three natively, so this costs attributes at drawing time and nothing afterwards. Left out of a first increment it becomes a retrofit across every component — the reason it is decided here rather than deferred.

## Risks / Trade-offs

- **A composed deck is judged against a designer's.** A plain composition on a plain template is a real improvement over nine cover slides, but it will not match a designed slide. The fallback ordering (D5) keeps it out of the way whenever the template can do better.
- **Palette role detection is a heuristic.** A theme colour's role comes from the theme's own slots, but templates misuse those slots. Mitigation: fall back to the text colour the master actually uses, and never invent a colour.
- **The classification rule can be wrong about intent.** Four short items are usually a card row, but sometimes they are genuinely a list. Mitigation: the author can exclude composed patterns and turn composition off entirely; and prose is protected explicitly (D9).
- **More surface to keep on-charter.** Every new component is a new way to look wrong. Mitigation: the fixed variant sets of D6, each validated visually on the reference template and on the stripped one, and the declared degenerate cases.
- **A theme reference can resolve to something the analysis never saw.** Referencing the theme is what makes a deck follow a later theme change — and it means the colour on the slide is whatever the theme says at open time, not what contrast was measured against. Mitigation: pairs are measured on the theme as stored, and a token with no slot to reference is recorded rather than silently written as a literal.
- **Splitting a slide changes what the agent planned.** A continuation slide the agent did not ask for can break a narrative the agent built. Mitigation: it is bounded to one per planned slide and always reported, so the agent can tell the user or re-plan.
- **`ANALYSIS_VERSION` bump re-analyses every agent on its next save.** Already the mechanism in place; the cost is the analysis time measured in `ppt-builder-capability`.

## Migration Plan

Additive. `PatternSource` gains a value and `TemplateInventory` a field; inventories stored without them keep loading, and the version bump recomputes them on the next save from the template already stored. No data migration, no config rewrite.

## Resolved Questions

- **An author can turn composition off for the whole agent**, not only pattern by pattern: one config field, "use only the slides of my template". Decided because an author who wants strict control of the charter should say it once, and should not have to redo it each time the template changes and the composed set is recomputed.
- **The delivered deck carries no mark of what was composed.** The tool result already names the composed slides, so the agent can tell the user; writing it into the speaker notes would show in presenter mode and travel with a deck shared as is.
- **The fallback rule reads `_shown_fields`, not `score_pattern`** (D5) — the first writing of this design said the ranking score could carry the decision. It cannot.
- **Emphasis asked for by the plan leaves this change** (D16) — it does not address the failure being fixed, and keeping it would block the archive.

### D17. The canvas carries the template's furniture, and never gets drawn on

A logo, a band, a rule or a footer placed on a slide master or a slide layout is not copied onto each slide: PowerPoint **inherits** it onto every slide using that layout. A composed slide therefore already shows the template's furniture, for free — provided two things hold.

**The canvas must be the dressed layout, not the barest one.** The first implementation chose, among the layouts with nothing to fill, the one with the fewest shapes. That is exactly backwards: a layout's own shapes are the charter, so the layout carrying the most of them is the one that makes a composed slide look like the rest of the deck. It qualifies only if what it leaves free still holds a slide — a block across the middle is a section divider, and nothing can be composed round it without splitting the page in two. A layout that switches the master's shapes off (`showMasterSp="0"`) inherits nothing, and that is read rather than assumed.

**What is inherited is reserved.** The footprint of every inherited fixture is measured and trimmed out of the usable area before the grid is built, edge by edge, taking whichever trim leaves the most room — a logo, a band or a footer sits at an edge, so that is the trim the designer intended. The full-bleed background is not a fixture, or nothing would be left; nor is a placeholder, which is what a slide fills. A fixture in the middle cannot be trimmed around, and a layout carrying one is simply not used as a canvas.

The renderer keeps a net under this: any composed shape overlapping a reserved fixture is reported. The grid already excludes them, so it only fires for a piece placed off the grid — which is how the title-anchor case in D13 was found.

### D18. The template's own blocks are read for their style, not copied

D5 says composition is the normal path and the template is the design language. That is only true if the language is read far enough. Tokens alone — colours, type, grid — produce something clean, on-charter and anonymous: it does not look like *this* company's deck, because what makes a deck recognisable is the hand, not the palette.

So the blocks the template draws for itself are read for what they demonstrate:

- **Painted or outlined.** A house that outlines its panels and one that fills them look nothing alike. Read from the shapes that actually paint something — a bare text box paints nothing and must not vote, or every plain template would be read as an outlining one.
- **The corner.** Read from those same painted blocks rather than from every `adj` value on the slide, which picks up arrows and callouts.
- **The air.** The inset a block gives its text, and the gap it leaves to the block beside it. The gap becomes the grid's gutter, so composed columns are spaced the way the template spaces its own; both are per-mille of the shorter side, like the spacing scale, so they stay comparable.
- **The figure and its label.** Whether a quantity sits above the words that name it or below. Read by finding a bare quantity and the nearest text sharing its column.

Every field has a defensible default, because a template that demonstrates none of this must still be composable, and "read, never invented" (D13) applies here too: a value the template does not show is not guessed, it is left to the scale.

Two boundaries this decision draws:

**Style is not structure.** "Does this composition have cards" is the composition's business; "are those cards painted or outlined" is the template's. Conflating them makes a template that outlines its panels produce slides with no panels at all — the first implementation did exactly that.

**The convention applies where it makes sense.** A Card follows the template's fill convention; a Bar, a Chip and a Divider are always painted. An outlined Bar shows nothing and an outlined Divider is two rules instead of one. Reading a template is not obeying it past the point where the result stops working.

### D21. A layout language, not a catalogue of flat compositions

*This supersedes the part of D6 that chose "a handful of well-proportioned compositions rather than a solver".* That choice was right for the first increment and is the ceiling of the second. Real corporate decks are built from **containers inside containers**: a panel holding a row of cards, each card holding an icon over a title over a paragraph. A flat list of fixed variants cannot express one of them, and adding variants until it can is how a catalogue becomes a swamp.

The target, stated the way the developer framed it: *compose like a designer on a free canvas, with the rules read from the template — as if the deck were written in HTML and delivered as clean PPTX that respects the corporate template.*

So the design layer gains a **box model**, and the analogy is exact and deliberate:

- A **node** is either a leaf that draws something (text, card, chip, bar, divider, image) or a **stack** that arranges children in a row or a column, with a gap, a padding, an alignment and its own surface.
- Sizing is `hug` (as big as the content) or `fill` (share what is left), which is flexbox's content-size and grow, and nothing more exotic.
- Resolution is the two passes every layout engine runs: **measure** bottom-up, each node reporting its natural size; **arrange** top-down, each parent handing its children a box. The output is absolute coordinates, because the output format has no flow.

What this does NOT become is a general constraint solver. There are no free variables: every gap comes from the spacing scale, every size from the type ladder, every colour from a token pair, every corner from the observed shape language. The engine only decides *where the boxes go* — the vocabulary stays the template's (D7, D11, D18).

What it buys, in order:

1. **Nesting**, which is the one thing missing from every real slide examined: a panel of cards, a card with a header band, a column of labelled rows inside a framed block.
2. **Compositions become declarations.** A card row stops being fifty lines of arithmetic and becomes a small tree. Adding one is then cheap enough that the library can actually grow.
3. **A path to letting the agent describe the structure** rather than pick from a catalogue — the real meaning of "write it in HTML". Not in this change, but the box model is the thing that makes it possible at all; a fixed catalogue never could.

Deliberately left out of reach, and this should be said plainly: the signature diagrams — a radial motif, a dense mosaic of heterogeneous cards, an annotated chart — are an author's work. The capability should generate the structural slides well and leave those to the template's own slides, which is exactly what `ppt_filler` is for.

### D22. The template's icons are a resource, and only named ones are offered

A corporate template usually carries a bank of icons — a slide of pictures and nothing else. The analysis already recognised that shape and excluded it from rendering; it then threw the icons away. They are the template's own assets, and a card led by one looks like the charter in a way no arrangement of text can.

So the bank is read for what it holds, with one rule: **only icons the template names are offered.** An icon called "Picture 12" or "logo.png" cannot be chosen meaningfully by anyone, and placing icons by turn would be decoration by lottery — worse than no icon. The name comes from the shape's alt text, then its title, then its own name, rejecting what PowerPoint invents and what an import left behind.

An icon is not a zone: it is not content the plan writes, it is an asset chosen by name. So an item carries an `icon`, the agent is shown the list, and a frame nobody named is removed rather than left as an empty box. A template with no named icon simply has no icon composition in its catalogue, and loses nothing else.

The aspect is read from the shape's real EMU and never from its per-mille box: the two axes have different scales, so a square icon read per-mille comes out wide and gets stretched back into its frame.

### D19. A piece takes the rung of the scale its box can carry

*Added after the first decks were built.* The type scale is read from the master's own styles, which size a **full-width placeholder**. A third of a slide is not a full-width placeholder: at the master's body size a card held 21 characters of heading and 75 of text, and every card truncated.

So a piece does not take its role's size; it takes the largest rung of the template's scale whose text fits its box — width *and* height, because a smaller size buys lines as well as characters. No size is invented: a template whose smallest rung is still too big simply lands on that rung, and the truncation report says so.

Two things this must not break, each learned by breaking it:

- **The slide title keeps its own size.** An early threshold pushed a 40pt title down to 20pt because 880 per-mille "only" held 42 characters. Titles are short; the budget per role has to reflect what the role actually carries.
- **The hierarchy holds.** Two roles stepping down independently can land on the same rung — 16pt over 15pt reads as one undifferentiated block. Within one item, a heading is stepped back up to the rung above its body.

### D20. A Card is sized by what it holds, then resized to what it holds

A Card that stretches down the whole content band whatever it carries is the single most recognisable mark of a generated deck. It happened because the Card was given the column, and the column was the band.

Two steps, because a fixed-layout format cannot reflow:

1. **At composition time** the Card is drawn to the height of the rows it stacks, not to the band. The variant still declares a generous capacity — the agent must be free to write a full card — so the declared height is what a *full* card needs.
2. **At render time**, once the text is in, each Card is resized to what its text actually takes, and every Card of a row takes the tallest so the row stays a row.

The alternative — declaring a small capacity so the card is never empty — was rejected: it makes the deck thin, which was the other half of the same complaint.

Deliberately NOT done: centring the row in the band when the cards come out short. It would break the cross-slide alignment of D13, which is worth more than the balance of one slide.

### D16. Emphasis asked for by the plan is a later change

This change gives the agent no way to mark a word or a figure as emphasised. Hierarchy comes from the components instead: a figure is large because it sits in a Stat, a statement is large because it is a statement.

Decided with the developer on 2026-09-25. Emphasis does not address the failure this change exists to fix — a deck of repeated bullet lists — and it enlarges the vocabulary the agent has to handle correctly, which the September sessions showed is where a smaller model degrades. What it would add over component-carried hierarchy is the ability to pick out a word inside a paragraph: real, but the least pressing of the things missing.

Keeping it here would also block the archive: a task section deliberately left undone means the capability spec never becomes current. So it leaves as its own change rather than sitting open in this one, and the requirement drafted for it is withdrawn from this delta rather than promising behaviour that will not ship with it.

The accent economy rule stays (D6) — it governs the colours components themselves carry, and does not depend on the plan being able to ask for anything.
