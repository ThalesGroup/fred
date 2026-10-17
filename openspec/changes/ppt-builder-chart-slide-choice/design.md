## Context

`assign._beam` picks one template slide per plan slide. Each candidate carries a fit cost (`misfit`: kind step, layout, unfilled zones, unused items, shrink) and the beam adds variety prices per path: `_REUSE` 8 per earlier use in the section, `_REPEAT` 3 for the same slide twice in a row, `_TRIPLE` 1000, `_OVER_MAX` 100 beyond `variety_max_uses`. An unfilled text zone costs `_EMPTY_ZONE` 1.5, an empty picture `_IMAGE_HOLE` 4. Variety therefore beats fill as soon as one reuse is priced: the owner's eleven chart-only slides went round three chart slides, two of which left their text box empty.

## Goals / Non-Goals

Goals: a slide never takes a template slide that leaves more zones unfilled only for variety; variety still alternates between equally filled slides; the built-in "Fred Chart" / "Fred Chart Wide" behaviour holds.

Non-goals: changing the fit costs themselves, the kind tiers of other kinds, the variety ask's wording, `like` or the design pin.

## Decisions

### D1. Dominated fits leave the candidates (Pareto, per kind)

`misfit` also counts the zones a fitting pattern leaves unfilled (`_weigh`: text zones swept away, empty picture zones, item picture holes; the same places that already add `_EMPTY_ZONE` / `_IMAGE_HOLE`). `_fullest` drops a candidate when another candidate **of the same kind** leaves fewer zones unfilled **at no higher fit cost**. Such a candidate could only ever be chosen for variety: the fit already prefers the other one. What remains is priced exactly as before.

Alternatives considered:

- *Lexicographic cost (unfilled zones first, then the rest)*: would also override fit trade-offs the costs encode on purpose (an example slide with an empty subtitle outranks a bare layout, `_LAYOUT` 5), and across kinds would beat the requested kind. Rejected.
- *Waiving reuse prices when the alternative leaves a zone empty*: the same outcome, but non-local inside the beam (depends on the path), harder to read. Rejected.

### D2. Scope: all kinds

The mechanism is generic (one count, one filter) and the principle is the owner's, not chart-specific. Close-kind rules are untouched: the filter only compares candidates of one kind, so a requested kind is never traded for another, and the tier order still decides first. Effects outside charts, all intended: `variety_max_uses` no longer pushes a slide onto a variant with an empty picture or zone while a fuller one of its kind fits (the reuse is then priced, as when the kind has one variant); five bullets slides no longer take a variant with an extra empty label box. The variety ask leaves those variants out of its "unused variants" (`_repeats`), like a variant with the group's own fit problem: asking to recast onto them would bring back the empty zone through the model.

### D3. The design pin is kept

`_kept` keeps the delivered slide's template slide before the filter applies: a text edit on a slide built on a now-dropped variant keeps its design (same rule as before: the pin holds while it fits).

### D4. A chart without a requested kind: chart slides first

A plan slide with a chart and no `kind` had one tier `[chart, bullets, two_columns, image_text]`, so variety (`_REUSE` above `_KIND_STEP` from the second reuse) could move it into a content area. Once D1 removes the emptier chart slides, that became the variety outlet. `_tiers` now puts `chart` in a tier of its own first, as when `chart` is asked: a content area only when no chart slide holds it. Consistent with `ppt-builder-charts` D8 (a chart's data has one natural form).

### D5. Effect on the owner's template and the built-in one

- Owner's template: chart-only slides all take the centred slide, consecutively if needed (three in a row is the only fit, the passive note says nothing else suits them); chart + text slides take the two side slides, alternating (both fill all zones, variety arbitrates).
- Built-in: a bare chart takes "Fred Chart Wide" (the takeaway variant is dropped, its body would be empty); a chart with a takeaway text still goes beside the chart on "Fred Chart" (fit cost lower, nothing dropped). `ppt-builder-charts` D10's "the empty takeaway costs the narrow variant a fit point, so the wide one wins" held only for the first use; this change makes it hold for every use.

### D6. An empty takeaway card weighs two zones (owner decision 2026-10-17)

The built-in deck v3 gave "Fred Chart Wide" a one-line caption, so a bare chart left one zone unfilled on either chart slide and D1 no longer separated them: variety alternated the wide slide with the card slide, whose removed card left the right third blank. `_weigh` now counts an unfilled takeaway zone (`Zone.takeaway`) as two unfilled zones and two `_EMPTY_ZONE` costs: a card swept away leaves a large blank, a caption a line. Variety still alternates between equally filled variants. The takeaway rule of `ppt-builder-capability` Q10 is untouched: with the takeaways asked, the card is filled, so the card slide wins.

Alternative considered: weighting every unfilled zone by its area. More general, but it re-prices every kind; rejected as broader than the reported case.

## Risks / Trade-offs

- Less variety on templates whose variants differ only by an extra zone: a deck may repeat one template slide more, including three in a row when nothing else fills as well. Accepted by the owner; the passive note still reports the run.
- A kind-less slide may move to another kind of its inferred tier earlier than before (the emptier same-kind variant no longer absorbs the reuse price). Only another kind that fits all its content, as before.

## Owner decisions


- 2026-10-16: the owner approved the behaviour: "pick the template slide that leaves the fewest unfilled zones; fewer empty zones beats variety"; chart-only slides all on the centred slide even consecutively, chart + text slides on the side slides, variety alternating between those two.
- 2026-10-17: a bare chart always takes the full-width chart slide; a removed takeaway card counts as an unfilled zone large enough to lose to it (D6).
