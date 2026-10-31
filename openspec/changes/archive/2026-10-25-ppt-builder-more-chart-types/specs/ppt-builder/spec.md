## ADDED Requirements

### Requirement: More native chart types

The system SHALL accept, besides the seven types of the chart requirement, the chart types `stacked_bar`, `radar`, `scatter` and `bubble`, and SHALL build each as a native, editable PowerPoint chart (`BAR_STACKED`, `RADAR_MARKERS`, `XY_SCATTER`, `BUBBLE`) placed only in a chart zone or a free chart-capable placeholder, with theme accent colours, the theme body font and a code-decided legend, labels and number formats. `stacked_bar` and `radar` SHALL take categories and series values; a radar SHALL have between 3 and 8 categories. Each chart SHALL keep one measure on each axis: `stacked_bar` and `radar` SHALL follow the one-measure checks of their single value axis, including the spread question. Every refusal SHALL be a `needs_revision` problem naming what is wrong and how to fix it; no data SHALL be cut or rescaled.

#### Scenario: Horizontal stacked bar

- **WHEN** the model sends `chart: {type: stacked_bar, categories: [Sales, R&D, Support], series: [{name: 2025, values: [4, 3, 2]}, {name: 2026, values: [5, 3, 3]}]}`
- **THEN** the delivered slide holds a native horizontal stacked bar chart in the chart zone, its series filled with `accent1` and `accent2`

#### Scenario: "Stacked bar" in words

- **WHEN** the model sends a chart whose type is written "stacked bar"
- **THEN** a horizontal stacked bar chart is built, not a stacked column chart

#### Scenario: Radar with too few criteria

- **WHEN** the model sends a `radar` chart with two categories
- **THEN** no deck is built and `needs_revision` says a radar needs 3 to 8 criteria, or to use `column` or `bar`

#### Scenario: Radar mixing scales

- **WHEN** a `radar` chart without `unit` has values from 2 to 900
- **THEN** the call is refused once with the question whether the values measure the same thing, as for a column chart

### Requirement: Scatter and bubble charts take numeric points

For `scatter` and `bubble`, the system SHALL accept series made of points, each with a numeric `x` and `y` (and, for `bubble`, a positive `size`) and an optional short `label`, plus axis titles `x_title` and `y_title` and optional units `x_unit` and `unit` (and `size_title`, `size_unit` for `bubble`). The system SHALL require both axis titles, SHALL check that the values of each axis carry one unit, SHALL NOT ask the spread question for these types, and SHALL cap points (scatter 3 to 50, bubble at most 15). A scatter or bubble sent with non-numeric categories, or a category chart sent with points, SHALL be a `needs_revision` problem naming the type to use; numeric categories with values SHALL be read as x values. The points' numbers SHALL count as the slide's figures for the source checks.

#### Scenario: Scatter built from points

- **WHEN** the model sends `chart: {type: scatter, x_title: Price, x_unit: €, y_title: Units sold, series: [{name: Products, points: [{x: 10, y: 120}, {x: 15, y: 90}, {x: 22, y: 60}]}]}`
- **THEN** the delivered slide holds a native XY scatter chart with markers only, its axes titled "Price (€)" and "Units sold"

#### Scenario: Scatter written as categories

- **WHEN** the model sends a `scatter` chart with categories `[Q1, Q2, Q3]` and series values
- **THEN** no deck is built and `needs_revision` says a scatter takes points and to use `line` or `column` for categories

#### Scenario: Missing axis title

- **WHEN** a `scatter` chart has no `x_title`
- **THEN** `needs_revision` asks what the horizontal axis measures

#### Scenario: One unit per axis

- **WHEN** the x values of a `scatter` are written "10 €", "12 %" and "15 €"
- **THEN** `needs_revision` says the x values mix units and a chart axis shows one measure

#### Scenario: Bubble size must be positive

- **WHEN** a `bubble` point has `size: 0`
- **THEN** `needs_revision` names that point and says a bubble needs a positive size

#### Scenario: Points are sourced figures

- **WHEN** a `scatter` slide carries no `source`
- **THEN** `needs_revision` asks for the source of the slide's figures, as for any chart
