## ADDED Requirements

### Requirement: Shared calendar clock for CSS themes

Fred SHALL publish the Europe/Paris civil date as `data-calendar-date` and seconds since midnight as the unitless CSS custom property `--fred-seconds-since-midnight` on the document element. It SHALL sample both from the same instant at startup, at least once per visible minute and when a tab returns to the foreground.

#### Scenario: Visitors in different time zones

- **WHEN** two visitors with accurate device clocks open Fred at the same instant
- **THEN** their theme clock reflects the same Paris civil date and time regardless of their browser time zones

#### Scenario: Overnight tab

- **WHEN** a visitor leaves a tab open across Paris midnight or resumes a background tab
- **THEN** the clock reflects the new date and time without a page reload
