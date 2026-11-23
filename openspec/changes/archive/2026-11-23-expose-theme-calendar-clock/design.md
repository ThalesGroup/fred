## Context

A CSS-only ZIP can style the active theme but cannot read a wall clock.

## Decisions

Publish the Paris civil date in YYYY-MM-DD format and seconds since local midnight as a unitless CSS number. Use one browser clock reading for both, formatted explicitly in Europe/Paris. Refresh on mount, at minute boundaries and on tab return. This keeps users with reasonably accurate device clocks within a minute and requires no backend traffic.
