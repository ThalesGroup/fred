## ADDED Requirements

### Requirement: Variety never leaves a zone unfilled

When choosing the template slide for a plan slide, the assignment SHALL NOT take a template slide that leaves more zones unfilled (text zones swept away, empty pictures) than another fitting template slide of the same kind whose fit cost is not higher. Reuse, repeat and maximum-use prices SHALL only choose between the remaining template slides. The variety ask SHALL NOT offer such a template slide as a variant to recast to. A slide keeps the template slide it was delivered on while that one still fits. A chart slide without a requested kind SHALL take a chart template slide before a content area. An unfilled takeaway zone SHALL count as two unfilled zones, as removing it leaves a side of the slide blank; when the user asked to see the takeaways and the slide's takeaway fits that zone, the template slide holding it is still preferred.

#### Scenario: Bare charts keep the centred chart slide

- **GIVEN** a template with a centred chart slide (title and chart) and two chart slides with a text box beside the chart, and `variety_max_uses` 1
- **WHEN** a deck of six slides each holding only a title and a chart is assigned
- **THEN** every slide takes the centred chart slide, and no variety ask is returned

#### Scenario: Charts with text alternate the side slides

- **GIVEN** the same template
- **WHEN** a deck of four slides each holding a title, a chart and bullets is assigned
- **THEN** they take the two side slides, never the same one twice in a row

#### Scenario: Built-in chart slides

- **GIVEN** the built-in template
- **WHEN** one chart slide with a takeaway text and one bare chart slide are assigned
- **THEN** the first takes "Fred Chart" (text beside the chart) and the second "Fred Chart Wide"

#### Scenario: Bare charts take the full-width slide even with a caption

- **GIVEN** the built-in template, whose full-width chart slide has a one-line caption and whose other chart slide has a takeaway card beside the chart, and `variety_max_uses` 1
- **WHEN** four slides each holding only a title, a chart and a takeaway not asked on the slides are assigned
- **THEN** every slide takes the full-width chart slide; with the takeaways asked on the slides, they take the slide with the card

#### Scenario: Max uses never forces an empty zone

- **GIVEN** `variety_max_uses` 1, a bullets example slide and a bullets layout with an extra picture zone
- **WHEN** two bullets slides without pictures are assigned
- **THEN** both take the bullets example slide; with a second bullets variant that fills all its zones, the second slide takes that variant
