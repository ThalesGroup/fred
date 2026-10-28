## ADDED Requirements

### Requirement: A KPI tile with a per-bucket series opens its trend

The Analytics page SHALL offer a "show trend" button on each tile or funnel step whose value has a per-bucket series in `analytics_activity_over_time`, and on no other. The button SHALL open a dialog showing that value over the selected period, read with the page's scope, user filter, time zone and bucket.

#### Scenario: An additive value

- **WHEN** an admin opens the trend of conversations, messages, cost, tokens or footprint
- **THEN** the dialog shows a cumulative line per bucket
- **AND** its last point equals the tile value

#### Scenario: A distinct count

- **WHEN** an admin opens the trend of active users or visitors
- **THEN** the dialog shows a line of the count per bucket
- **AND** a note gives the period value and says a person active in several buckets counts once

#### Scenario: A tile without a series

- **WHEN** a tile's value has no per-bucket series (a median, a rate, a current-state count)
- **THEN** the tile shows no trend button
