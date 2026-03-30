"""
Explicit home for v2 code that still bridges legacy Fred shapes.

Why this package exists:
- pure v2 runtime code now lives in `contracts/`, `react/`, `support/`, and the
  dedicated runtime modules
- the files here still depend on legacy `AgentSettings`, legacy
  `RuntimeContext`, or the old factory/service stack
- keeping them together makes the migration boundary easy to review and later
  remove
"""
