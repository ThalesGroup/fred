## ADDED Requirements

### Requirement: Counted days

The analytics pages SHALL let the viewer leave weekends and French public
holidays out of every activity figure and the export, both left out by
default, the choice kept per viewer. Per-day averages SHALL divide by the
counted days.

#### Scenario: Weekend left out

- **GIVEN** weekends are not counted
- **WHEN** a 7-day period holding a weekend is read
- **THEN** no figure counts the weekend's events
- **AND** per-day averages divide by the 5 counted days
