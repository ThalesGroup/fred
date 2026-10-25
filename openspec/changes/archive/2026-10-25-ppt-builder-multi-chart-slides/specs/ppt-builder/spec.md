## ADDED Requirements

### Requirement: Template slides with several charts are filled

The system SHALL treat every chart frame of a template slide that is not grouped, not declared `keep` and covers at least 5 % of the slide as a chart zone, up to four per slide, numbered in reading order (top to bottom, then left to right). Such a slide SHALL be offered as a chart slide whose catalogue entry states how many charts it holds. A slide still holding a chart that is not a chart zone SHALL stay excluded, with its current exclusion reason.

The plan SHALL accept `charts`, a list of charts, beside the one-chart field `chart`, which SHALL keep its current behaviour; sending both on one slide SHALL be a `needs_revision` problem. A slide planned with k charts SHALL be built only on a template slide with exactly k chart zones, the i-th chart filling the i-th zone; when the template offers no such slide, the call SHALL be refused with `needs_revision` naming the chart counts the template offers and how to reach one (split the slide, or merge or drop charts). The tool SHALL NOT draw a chart outside a chart frame of the template.

Each chart SHALL follow every chart rule on its own: offered types, theme accent colours and body font, validation and fit measured on its own frame, the example chart's formatting kept when its type matches, one measure per chart. Each problem SHALL name the chart as `charts[i]`. On a slide with several charts each chart SHALL have a title; the slide SHALL keep one takeaway and one source. Edits SHALL address a chart as `charts[i]`, and an edit changing the number of charts SHALL move the slide to a template slide with the new count, or be refused as above. The delivered slide SHALL hold as many native charts as planned, each with its own chart data.

#### Scenario: Two-chart example slide is offered

- **WHEN** a template slide holds two chart frames of 24 % of the slide each
- **THEN** analysis keeps the slide as a chart slide with two chart zones, left one first, and the catalogue lists it with `charts×2`

#### Scenario: Four small charts are offered

- **WHEN** a template slide holds four chart frames of 9.3 % of the slide each, in a two-by-two grid
- **THEN** analysis keeps the slide with four chart zones ordered top-left, top-right, bottom-left, bottom-right, and it is no longer excluded as `unsupported_parts`

#### Scenario: A chart too small to fill

- **WHEN** a template slide holds a chart frame covering 3 % of the slide that is not declared `keep`
- **THEN** the slide stays excluded with its current reason

#### Scenario: Two charts filled in place

- **WHEN** the model sends a slide with `charts` holding a `column` chart titled "Revenue" and a `pie` chart titled "Revenue by region", and the template's two-chart slide shows an example column chart then an example pie chart
- **THEN** the delivered slide holds the two example charts refilled with the plan's data, their formatting kept, in the template's places

#### Scenario: No slide with that many charts

- **WHEN** the model sends a slide with three charts and the template offers slides with one, two and four charts
- **THEN** no deck is built and `needs_revision` says the template offers 1, 2 or 4 charts per slide and suggests splitting the slide or merging charts

#### Scenario: One problem per chart

- **WHEN** the second chart of a `charts` list mixes '%' and 'M€' values
- **THEN** `needs_revision` names `charts[1]` and says a chart shows one measure

#### Scenario: Untitled chart among several

- **WHEN** a slide with two charts has a chart without `title`
- **THEN** `needs_revision` asks what that chart shows, naming `charts[i]`

#### Scenario: Single chart unchanged

- **WHEN** the model sends a slide with `chart` and the template has a one-chart slide and a two-chart slide
- **THEN** the slide is built on the one-chart slide, as before this change

#### Scenario: Editing one chart

- **WHEN** a change sends `{"op": "edit", "slide": 3, "field": "charts[1].series[0].values[2]", "value": 42}`
- **THEN** only that value of the second chart changes and the slide keeps its template slide
