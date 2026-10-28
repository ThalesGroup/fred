## Decisions

- **Holidays** are the eleven French public holidays, computed in code
  (Easter-based dates included), no new dependency.
- **Filtering**: excluded local days in `tz` become merged `must_not`
  `@timestamp` ranges in each search, previous period included; no script, no
  extra round trip. State presets ignore the parameters.
- **Denominators**: per-day figures divide by counted days; a week counts 5
  days when weekends are excluded.
- **Default**: the API counts every day; the page excludes both unless the
  viewer changes it (stored per viewer).
- Periods longer than four years with exclusions answer 400.
