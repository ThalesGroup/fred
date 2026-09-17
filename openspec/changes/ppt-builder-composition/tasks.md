## 1. Sequencing

- [ ] 1.1 Close and archive `ppt-builder-capability` (its task 7.1, the end-to-end pass, is what the September sessions exercised) so `openspec/specs/ppt-builder/spec.md` exists — verify: `openspec archive ppt-builder-capability` succeeds and `openspec validate ppt-builder-composition --strict` no longer reports that the target spec is missing

## 2. The design system

- [ ] 2.1 Read the theme's colour palette with the role of each slot, the type scale per text level, and the master's usable area and margins — verify: unit tests on the reference template and on a stripped one assert a palette, a scale and an area, and that a template misusing its theme slots still yields a text colour the master actually uses
- [ ] 2.2 Persist it in `TemplateInventory` and bump `ANALYSIS_VERSION` — verify: an inventory saved without it loads, and a save recomputes it from the stored template (the existing refresh test, extended)
- [ ] 2.3 Stop excluding a blank layout for holding no placeholder: it is the canvas — verify: the stripped template's `layout:1` is no longer excluded with `no_placeholder`

## 3. Composed patterns

- [ ] 3.1 Add `composed` to `PatternSource` and build composed patterns from the design system — a statement, a two-column split, a card row, a big figure, an agenda — each with zones, roles and boxes inside the usable area — verify: the stripped template yields a composed pattern for each of those intents, with every box inside the master's usable area
- [ ] 3.2 Render a composed pattern by drawing its zones on the blank canvas, then filling them through the existing path — verify: a rendered composed slide goes through the same fitting, truncation and reporting as a template pattern (assert on the warnings, not on the drawing)
- [ ] 3.3 Enforce that no colour, typeface or size reaches a shape unless it came from the design system — verify: a test that walks a composed slide's XML and fails on any value absent from the palette and type scale
- [ ] 3.4 Restate the invariant in `render.py`'s docstring and in `design.md` of the archived change's compact doc if it restates it — verify: no doc still claims the renderer never draws

## 4. Choosing between template and composition

- [ ] 4.1 Compose only when the best included template pattern would lose content, using `score_pattern` — verify: on the reference template a nine-slide plan composes nothing; on the stripped one the `content`, `cards` and `statement` slides are all composed and none lands on the cover
- [ ] 4.2 Report composed slides in the tool result — verify: the result names them and the deck itself carries no mark
- [ ] 4.3 Add the agent config field "use only the slides of my template" and honour it — verify: with it set, the stripped template composes nothing and reports the lost content as today; the setting survives a re-analysis

## 5. Emphasis

- [ ] 5.1 Add optional emphasis to slide and item content, resolved through the design system, with no way to name a colour, typeface or size — verify: an accented bullet takes a palette colour; an unknown emphasis renders plain and is reported, and never fails the call
- [ ] 5.2 Name the emphasis vocabulary in the tool description — verify: the description lists the roles and the catalogue test asserts them

## 6. Review surface

- [ ] 6.1 Render composed patterns into the patterns deck the review widget previews — verify: the widget shows a thumbnail for a composed pattern with no source slide, through the existing code path
- [ ] 6.2 Surface the agent-level switch in the config widget — verify: toggling it in the form round-trips through save and reload

## 7. Verification

- [ ] 7.1 Visual pass: build a deck on the stripped template and on the reference one, convert and read every slide — verify: the stripped deck is varied and on-charter, the reference deck is unchanged from before this change
- [ ] 7.2 `make code-quality` and `make test` green in `libs/fred-capability-ppt-filler`; `fred-performance-reviewer` on the analysis path (composition runs at save and at render)
- [ ] 7.3 `/code-review` on the branch diff; apply fixes
- [ ] 7.4 Update `docs/swift/capabilities/AUTHORING.md` only if the capability authoring surface changed — verify: reread it against the diff and state the outcome either way
