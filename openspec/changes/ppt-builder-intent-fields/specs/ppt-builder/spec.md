## ADDED Requirements

### Requirement: Intent fields express meaning, never style

The system SHALL accept on a plan optional intent fields — `chart.highlight`, `chart.sort`, `chart.stacked_as`, `table.total_row`, `table.highlight_row`, `table.highlight_column`, `items[].trend` — whose values are a short enumeration, a boolean, or a reference to content already in the plan, and SHALL NOT accept a colour, font, size or position through them. Each field SHALL default to the rendering without it. The system SHALL decide how an intent looks from the template (theme colours, table style, the text style of the content it marks, a zone the template designed). When an intent cannot be rendered — its value or reference matches nothing, or the template or chart type cannot show it — the system SHALL still build the deck, SHALL send the agent a note naming the field and a remedy, and SHALL record `intent_not_shown` (or `intent_shown_otherwise` when a fallback rendered it) with the field on that slide's "What was built" entry. Intent fields SHALL be editable through `changes` like any other field, and SHALL be offered in the tool schema only when the template can render them.

#### Scenario: Intent left out

- **WHEN** the model sends a chart, a table and key figures with no intent field
- **THEN** the deck is the same as before this change, bar charts included

#### Scenario: Reference that matches nothing

- **GIVEN** a chart whose categories are Q1, Q2, Q3, Q4
- **WHEN** the model sends `highlight: "Nord"`
- **THEN** the deck is built without highlight, the agent note lists the valid categories, and the slide's summary entry holds `intent_not_shown` for `highlight`

#### Scenario: Colour sent as an intent

- **WHEN** the model sends `highlight: "red"`
- **THEN** no colour is applied and the slide's summary entry holds `intent_not_shown` for `highlight`

#### Scenario: Intent edited

- **GIVEN** a delivered deck whose slide 3 holds a chart
- **WHEN** the model sends `{"op": "edit", "slide": 3, "field": "chart.highlight", "value": "Q3"}`
- **THEN** the deck is re-rendered with Q3 emphasised on the same template slide

### Requirement: Chart emphasis

The system SHALL reorder a chart's categories with all their values for `sort: desc | asc` (by the first series, or by category totals for a stacked column), SHALL keep the given order for `given` and for line and area charts (with a note when a sort was asked), and SHALL draw a sorted bar chart with the first category of the resulting order on top, leaving an unsorted bar chart's order unchanged. For `highlight`, the system SHALL draw the named category (one-series column, bar and stacked column charts, pie, doughnut) or the named series (several series) in the theme's first accent and every other point or series in a muted colour derived from the theme text colour, and SHALL NOT write a literal colour; a category named on a one-series line or area chart SHALL be noted as `intent_not_shown`. For `stacked_as: percent` on a stacked column, the system SHALL build a 100 % stacked column.

#### Scenario: Sorted bar chart

- **WHEN** the model sends a bar chart with `sort: desc`
- **THEN** the largest value is the top bar and the plan keeps its categories in the order written

#### Scenario: Highlighted category

- **WHEN** the model sends a one-series column chart with `highlight: "Q3"`
- **THEN** the Q3 bar references `accent1`, the other bars reference the muted theme text colour, and no `srgbClr` is written

#### Scenario: Highlighted series

- **WHEN** the model sends a line chart with series 2024 and 2025 and `highlight: "2025"`
- **THEN** the 2025 line references `accent1` and the 2024 line is muted

#### Scenario: Percent stacking

- **WHEN** the model sends a `stacked_column` chart with `stacked_as: percent`
- **THEN** the chart is a 100 % stacked column with a percent value axis; and **WHEN** it sends `stacked_as: percent` on a `line` chart **THEN** the line chart is built and the summary holds `intent_not_shown` for `stacked_as`

### Requirement: Table and key-figure emphasis

For `table.total_row: true`, the system SHALL apply the table style's own total-row formatting, and SHALL fall back to bold text with `intent_shown_otherwise` when the style defines none; when `total_row` is false or absent the system SHALL NOT leave a template's total-row formatting on the last data row. For `highlight_row` and `highlight_column`, given as an index or as the row's first-cell text or the column's header text, the system SHALL emphasise that row or column with bold text and a tint of the table style's theme accent that differs from the style's own row bands, paler when the theme's dark text would not stay readable on it. For `items[].trend: up | down | flat`, the system SHALL show an arrow glyph before the item's figure in the figure's own text style, and SHALL NOT colour it by meaning.

#### Scenario: Total row on a predefined table style

- **GIVEN** a template table using a predefined table style
- **WHEN** the model sends a table with `total_row: true`
- **THEN** the delivered table's properties set the total-row flag and the last row's text is the plan's last row

#### Scenario: Template total row without a total

- **GIVEN** a template table whose properties set the total-row flag
- **WHEN** the model sends a table without `total_row`
- **THEN** the delivered table's total-row flag is off

#### Scenario: Highlighted row by its text

- **WHEN** the model sends `highlight_row: "Offer B"` and a body row's first cell is "Offer B"
- **THEN** that row's text is bold and its cells are tinted with the table style's accent, stronger than the style's banded and unbanded rows

#### Scenario: Highlight on a dark accent

- **GIVEN** a theme whose table accent is too dark for the theme's text on the strong tint
- **WHEN** the model sends a highlighted row
- **THEN** the row is tinted with a paler shade of the same accent and its text is bold

#### Scenario: Rising key figure

- **WHEN** the model sends a figures slide whose second item has `number: "42 %"` and `trend: up`
- **THEN** the second figure reads `▲ 42 %` with the glyph in the figure's own font and colour, smaller than the figure

#### Scenario: Trend without a figure zone

- **WHEN** the model sends `trend: down` on an item whose group has no number zone
- **THEN** the deck is built and the summary holds `intent_not_shown` for `trend`

### Requirement: Slide takeaway

The analysis SHALL mark at most one text zone per pattern as a takeaway zone when its shape name (or its layout placeholder's name) or its vision-labelled purpose names a takeaway or key message, and SHALL NOT mark one from geometry alone; a free text box so named SHALL be read as a body whatever its text size. By default the system SHALL leave the takeaway in the speaker notes only and SHALL fill a takeaway zone from the slide's content only when it is the slide's only body; beside another body it SHALL never be a column and SHALL be left empty (owner decision 2026-10-18: audit fixes). The system SHALL write the takeaway into the zone only when the plan sets `show_takeaways` (the field asks the model to set it only when the user explicitly asks for key messages to be shown; no word list second-guesses it), the assigned template slide has a takeaway zone and the takeaway fits its room; it SHALL then NOT fill that zone from `bullets`. In every other case the zone SHALL be filled or left empty as by default and the takeaway SHALL stay in the speaker notes, without a refusal; when `show_takeaways` is honoured the slide's summary SHALL then hold `intent_not_shown` for `takeaway`. The takeaway SHALL NOT change which kind of slide is assigned; a takeaway written into its zone SHALL count as filling that zone when slides of one kind are compared on the zones they leave empty, and with `show_takeaways` honoured the system SHALL prefer, among template slides of one kind, one that can show the takeaway over one that cannot.

#### Scenario: Takeaway kept off the slide by default

- **GIVEN** the built-in template
- **WHEN** the model sends, without `show_takeaways`, a chart slide with one bullet and `takeaway: "Q3 is our best quarter"`
- **THEN** the takeaway card holds the bullet as before this change and the takeaway is in the speaker notes only

#### Scenario: Takeaway in the template's zone on request

- **GIVEN** the built-in template and a user message "affiche les messages clés sur les slides"
- **WHEN** the model sends `show_takeaways: true` and a chart slide with `takeaway: "Q3 is our best quarter"`
- **THEN** the slide is built on the chart slide with the takeaway card, and the card holds that sentence

#### Scenario: The flag is the agent's, in any language

- **GIVEN** the user wrote "Zeig die Kernaussagen auf den Folien"
- **WHEN** the model sends `show_takeaways: true` and a chart slide with a takeaway
- **THEN** the takeaway card holds that takeaway

#### Scenario: Takeaway without a zone

- **GIVEN** a template whose bullets slide has no takeaway zone and a user message asking to show key messages
- **WHEN** the model sends `show_takeaways: true` and a bullets slide with a takeaway
- **THEN** the body holds the bullets only, the takeaway is in the speaker notes, and the summary holds `intent_not_shown` for `takeaway`

#### Scenario: Chart slides on request prefer the takeaway card

- **GIVEN** the built-in template and a user message asking to show key messages
- **WHEN** the model sends `show_takeaways: true` and two chart slides with a takeaway each
- **THEN** both are built on the chart slide with the takeaway card, each card holding its takeaway, rather than one on the wide chart slide

#### Scenario: Takeaway zone detected by name

- **GIVEN** a layout whose body placeholder is named "Key message"
- **WHEN** the template is analysed
- **THEN** that zone is a takeaway zone and the catalogue quotes its room

#### Scenario: A large box named for the key message

- **GIVEN** a free text box named "Message clé" whose sample text is 24 pt on one line
- **WHEN** the template is analysed
- **THEN** it is a body zone flagged as the takeaway zone, not a heading

#### Scenario: Takeaway longer than the zone

- **WHEN** the user asked to show key messages and the model sends `show_takeaways: true` with a chart slide holding one bullet and a takeaway longer than the built-in template's takeaway card holds
- **THEN** the bullet fills the takeaway card as before this change, the takeaway is in the speaker notes only, and the agent is told to shorten it
