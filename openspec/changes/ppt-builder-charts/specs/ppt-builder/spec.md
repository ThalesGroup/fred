## ADDED Requirements

### Requirement: Charts fill a chart zone the template offers

The system SHALL accept on a plan slide a `chart` field holding only data — `type` (`column`, `bar`, `line`, `pie`, `doughnut`, `stacked_column`, `area`), `categories`, `series` (each a `name` and one numeric value per category), an optional `title` and an optional `unit` — and SHALL NOT expose any colour, position, size, font or style field for it. The closed kind vocabulary SHALL include `chart`. The analysis SHALL expose as a `chart` zone every chart placeholder and every chart frame covering the main area of an example slide, and SHALL mark large content (`OBJECT`) placeholders as chart-capable. The code SHALL place the chart in a chart zone, else in a free chart-capable placeholder as a reported substitution, else return `needs_revision`; it SHALL never draw a chart outside such a zone. Charts SHALL be native, editable python-pptx charts whose series colours reference the template theme's accent colours and whose text references the theme's body font. When the chosen template slide is an example slide whose chart has the requested type, the system SHALL reuse that chart with its own formatting and replace only its data, and SHALL otherwise build a fresh chart.

#### Scenario: Chart placeholder becomes a chart slide

- **GIVEN** a template layout with a title placeholder, a chart placeholder and a body placeholder
- **WHEN** the template is analysed
- **THEN** the inventory holds a pattern of kind `chart` with a `chart` zone at the placeholder's box and the title and body zones

#### Scenario: Example chart slide is no longer excluded

- **GIVEN** an example slide whose chart covers the main area of the slide
- **WHEN** the template is analysed
- **THEN** the slide is an included `chart` pattern whose `chart` zone is the chart's frame, and its chart relationship does not make it uncopyable

#### Scenario: Native chart placed by the code

- **WHEN** the model sends a slide with `chart: {type: column, categories: [Q1, Q2, Q3], series: [{name: Revenue, values: [12, 15, 18]}]}` on a template with a chart slide
- **THEN** the delivered slide holds a native column chart in that slide's chart zone, editable in PowerPoint, with no broken or duplicate frame left from the example chart

#### Scenario: Colours come from the theme

- **WHEN** a fresh chart (not a reused example chart) with three series is rendered
- **THEN** the series fills reference the theme's `accent1`, `accent2` and `accent3`, and no literal colour is written

#### Scenario: Template without a chart slide

- **GIVEN** a template with no chart zone but a "Title and Content" layout whose content placeholder covers a large part of the slide
- **WHEN** the model sends a chart slide
- **THEN** the chart is placed in that content placeholder and the success message names the substitution

#### Scenario: Template with no place for a chart

- **GIVEN** a template with neither a chart zone nor a chart-capable placeholder
- **WHEN** the model sends a chart slide
- **THEN** no deck is built and `needs_revision` says the template has no slide for a chart, with options such as giving the data as a table, as key figures, or dropping the chart

#### Scenario: Key figures option counts every figures slide

- **GIVEN** a template with no place for a chart and several figures slides, the roomiest not last
- **WHEN** the model sends a chart whose values fit the roomiest figures slide
- **THEN** the options offer the values as items of a 'figures' slide

#### Scenario: Series length mismatch

- **WHEN** a series has fewer values than there are categories
- **THEN** no deck is built and `needs_revision` names the series, its value count and the category count

#### Scenario: Value that is not a number

- **WHEN** a value is written as `"12,5 %"`
- **THEN** it is read as 12.5; and **WHEN** a value is `"n/a"` **THEN** `needs_revision` names that value's path and asks for a number or the removal of its category

#### Scenario: Too much data for the zone

- **WHEN** a chart has more categories than its zone holds at a readable size, or more series than the cap, or a pie with several series
- **THEN** no deck is built and `needs_revision` gives the measured limit and a remedy (group as "Other", fewer series, another type); the chart is never cut or split over two slides

#### Scenario: Unsupported chart type

- **WHEN** the model asks for a chart type outside the offered list
- **THEN** the chart is built as a column chart and the delivery says so; the data is kept

#### Scenario: Data-only schema

- **WHEN** the model adds a colour or a position to its chart
- **THEN** that key is never applied, the deck is built, and the delivery note names the key as set by the template

#### Scenario: Chart edited through changes

- **GIVEN** a delivered deck whose slide 4 holds a chart
- **WHEN** the model sends `{"op": "edit", "slide": 4, "field": "chart.series[0].values[2]", "value": 21}`
- **THEN** the whole deck is re-rendered with that value changed and slide 4 on the same template slide

#### Scenario: Chart in the summary

- **WHEN** a deck holding a chart is delivered
- **THEN** the "What was built" entry of that slide shows kind `chart`, or the substituted kind with the requested `chart` noted

#### Scenario: Stacked column and area charts

- **WHEN** the model sends a chart of type `stacked_column` with two series, or of type `area`
- **THEN** the delivered slide holds a native stacked column chart (series stacked, a legend under the plot) or a native area chart, each series in the next theme accent

#### Scenario: Built-in template hosts charts

- **GIVEN** an agent without a configured template
- **WHEN** the model sends a chart slide with a takeaway in `bullets`, and another chart slide with only a title and the chart
- **THEN** the first is built on the built-in chart slide with a takeaway box, the second on the built-in full-width chart slide

#### Scenario: Template's own example chart reused

- **GIVEN** a template whose example chart slide holds a column chart
- **WHEN** the model sends a column chart that is placed on that slide
- **THEN** the delivered chart keeps the example chart's formatting (colours, fonts, axes) and shows the plan's categories, series and values; a chart of another type on that slide is a fresh theme-styled chart

### Requirement: Pie and doughnut labels show what the plan asks

The system SHALL accept on a chart an optional `show` field — `share`, `value` or `both`, unset meaning `share` — that sets what a pie's or doughnut's slice labels hold: percentages, the values with their `unit`, or the value then its percentage. The model SHALL NOT write a number format; the code SHALL derive it from `show` and `unit`. The system SHALL read loose spellings of `show` and its aliases `display`, `labels_as` and `show_as`, and SHALL keep `labels` as an alias of `categories`. The system SHALL NOT drop a label setting silently: a `unit` other than `%` on a pie or doughnut left in `share` SHALL be told to the model with the way to show it, and `show` on another chart type SHALL be told as not applied.

#### Scenario: Numbers instead of percentages

- **WHEN** the model sends a pie with `unit: "collaborateurs"` and `show: "value"`
- **THEN** the slice labels show `27 collaborateurs`, `15 collaborateurs`, `58 collaborateurs` and no percentage

#### Scenario: Value and percentage

- **WHEN** the model sends the same pie with `show: "both"`
- **THEN** each slice label shows the value with its unit, then its percentage on the next line

#### Scenario: Unit hidden by percentages is told

- **WHEN** the model sends a pie with `unit: "collaborateurs"` and no `show`
- **THEN** the labels show percentages, the delivery tells the model the unit is not shown and to set `chart.show` to `value`, and the "What was built" entry notes that the numbers are not displayed

#### Scenario: Labels mode edited through changes

- **GIVEN** a delivered deck whose slide 2 holds a pie labelled in percentages
- **WHEN** the model sends `{"op": "edit", "slide": 2, "field": "chart.show", "value": "value"}`
- **THEN** the deck is rebuilt with slide 2's labels showing the values, on the same template slide

#### Scenario: Labels mode on another chart type

- **WHEN** the model sends a column chart with `show: "share"`
- **THEN** the chart is built with its values and the delivery says `chart.show` was not applied, it sets a pie's or doughnut's labels only
