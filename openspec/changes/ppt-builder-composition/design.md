## Context

See proposal.md — Why. The relevant state: the analysis produces a `TemplateInventory` of patterns, each a layout or an example slide with typed zones; `plan.score_pattern` already measures, per slide, how much of the given content a pattern can show, weighted by what losing each field costs; the renderer instantiates or duplicates and fills, and its module docstring states that nothing is ever drawn. The theme's latin typefaces are already read, to measure text width.

Constraint that shapes everything below: the output is a `.pptx` people open and edit. Whatever is composed has to be real, editable PowerPoint shapes — not a picture of a slide.

## Goals / Non-Goals

**Goals:**

- A plain template (title layout, blank layout, closing slide) produces a varied, on-charter deck.
- A rich corporate template produces exactly what it produces today.
- Everything composed is traceable to a token read from the template.

**Non-Goals:**

- Free-form design. The agent never chooses a colour, a typeface, a size or a coordinate.
- Replacing the pattern inventory. Composition is the fallback, not the default.
- A second authoring format (see D4).
- Charts, tables and SmartArt: still out of scope, as in `ppt-builder-capability`.

## Decisions

### D1. Sequencing: archive `ppt-builder-capability` first

This change's delta carries a MODIFIED requirement, and `openspec archive` refuses that while the target spec does not exist. `ppt-builder-capability` has one open task (7.1, the end-to-end pass on the local stack, which the September sessions have exercised). It is archived first, folding its delta into `openspec/specs/ppt-builder/spec.md`; this change then modifies a real spec. Alternative — making every delta here ADDED — was rejected: it would leave two contradictory statements of the same requirement, one saying the renderer never adds a shape.

### D2. The design system is part of the inventory, not a second artifact

The palette, type scale and usable area are persisted inside `TemplateInventory`, beside `patterns`. Alternative considered: a separate stored asset. Rejected — the inventory is already the one thing a save recomputes and a version bump refreshes (`ANALYSIS_VERSION`), and splitting would give two things to keep in step for no gain.

### D3. Composed patterns are patterns

`PatternSource` gains `composed`. A composed pattern carries zones with roles and boxes like any other, so the renderer's filling, fitting, truncation and reporting all apply unchanged, and the author review surface, the catalogue and the scoring need no special case. What differs is only creation: instead of instantiating a layout or duplicating a slide, the renderer draws the zones onto the blank canvas first.

Alternative considered: a separate "composition" path parallel to the pattern path. Rejected — it would duplicate the fitting and reporting machinery this capability spent its whole first change getting right.

### D4. One tool, not several

Composition stays behind the existing `build_presentation` tool. A capability may expose several tools, and this one already does (`list_images_in_folder`), but splitting the build — "compose a slide" beside "build the deck" — would reintroduce the failure the September sessions showed: a small model splitting one deck across several calls and delivering several truncated decks. One call, one deck, remains the rule.

Revisit if the emphasis and layout vocabulary grows past what one legible schema can carry. A read-only tool exposing the design system (what the template can and cannot do) is a cheaper first step than splitting the build, and would follow the shape of `list_images_in_folder`.

### D5. The fallback rule reuses the existing measure

`score_pattern(pattern, slide)` already answers "how much of this content can this pattern show". A slide is composed when the best included pattern's score says content would be lost — the same threshold that already drives degradation between intents. No second heuristic, and the rule is testable: given a plan and an inventory, the choice is deterministic.

Alternative considered: compose whenever the agent asks for an intent the template lacks. Rejected — the template often has a usable neighbouring pattern, and preferring the designer's work is the whole point of D5's ordering.

### D6. Layout of a composed slide

Boxes are placed inside the master's usable area on a coarse grid derived from it, with the type scale deciding sizes. Deliberately a small, fixed set of arrangements rather than a solver: a handful of well-proportioned compositions beats a general layout engine that occasionally produces something odd, and each can be reviewed visually once and trusted.

### D7. The invariant, restated

"Nothing is ever drawn: the corporate design cannot be broken" becomes "nothing is drawn outside the template's own design tokens". The guarantee is no longer procedural (we never draw) but material (what we draw cannot leave the charter). It is enforced where the drawing happens, so a colour or size that is not a token cannot reach a slide.

### D8. Review surface for a pattern with no source slide

Composed patterns have no slide in the template to thumbnail. They are rendered into the same patterns deck the review widget already previews, so the widget keeps one code path.

## Risks / Trade-offs

- **A composed deck is judged against a designer's.** A plain composition on a plain template is a real improvement over nine cover slides, but it will not match a designed slide. The fallback ordering (D5) keeps it out of the way whenever the template can do better.
- **Palette role detection is a heuristic.** A theme colour's role (accent, background, text) comes from the theme's own slots, but templates misuse those slots. Mitigation: fall back to the text colour the master actually uses, and never invent a colour.
- **More surface to keep on-charter.** Every new composition is a new way to look wrong. Mitigation: the fixed set of D6, each validated visually on the reference template and on the stripped one.
- **`ANALYSIS_VERSION` bump re-analyses every agent on its next save.** Already the mechanism in place; the cost is the analysis time measured in `ppt-builder-capability`.

## Migration Plan

Additive. `PatternSource` gains a value and `TemplateInventory` a field; inventories stored without them keep loading, and the version bump recomputes them on the next save from the template already stored. No data migration, no config rewrite.

## Resolved Questions

- **An author can turn composition off for the whole agent**, not only pattern by pattern: one config field, "use only the slides of my template". Decided because an author who wants strict control of the charter should say it once, and should not have to redo it each time the template changes and the composed set is recomputed.
- **The delivered deck carries no mark of what was composed.** The tool result already names the composed slides, so the agent can tell the user; writing it into the speaker notes would show in presenter mode and travel with a deck shared as is.
