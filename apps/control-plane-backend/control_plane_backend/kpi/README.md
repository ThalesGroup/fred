# KPI presets

Each KPI preset is a self-contained query that runs against OpenSearch and returns
structured data. Presets are auto-registered as GET endpoints under `/kpi/presets/<name>`.

## How it works

```
api.py          — iterates PRESETS, mounts one route per preset, resolves KpiScope
scope.py        — resolve_kpi_scope(): the ONE authorization chokepoint (see below)
presets/
  __init__.py   — PRESETS list (add your preset here)
  base.py       — PresetDef dataclass (team_scopable flag)
  common.py     — shared response types (TimeSeriesResponse, …)
  <name>.py     — one file per preset
utils.py        — resolve_interval(): picks OpenSearch bucket size from time range
                  resolve_trend_interval(): the same, plus the trailing window
```

Every preset is a `PresetDef`:

```python
PresetDef(
    name="my_preset",          # becomes GET /kpi/presets/my_preset
    response_model=MyResponse, # Pydantic model — drives OpenAPI schema
    handler=query_my_preset,   # called with (store, user=…, since=…, until=…, request=…[, team_ids=…])
    summary="One-line description for OpenAPI docs",
    team_scopable=False,       # True only if the underlying KPI event carries dims.team_id
)
```

The handler receives:
- `store: OpenSearchKPIStore` — call `store.client.search(index=store.index, body=…)`
- `user: KeycloakUser`, `request: Request` — authorization is already resolved by the
  router before the handler runs (see below); handlers keep these params (the router
  always passes them) but never call `check_user_permission_or_raise` themselves —
  `del user, request` if unused, matching the existing repo convention for
  intentionally-unused params.
- `since / until: datetime` — the requested time range (UTC, always set)
- `team_ids: Sequence[TeamId]` — **only** passed when `team_scopable=True`. Empty means
  platform-wide; otherwise add `common.team_filter(team_ids)` (a `terms` clause on
  `dims.team_id`) to the query filters.

## Authorization — one chokepoint, not one per preset

`resolve_kpi_scope(request, user, team_ids)` (`scope.py`) is called once by the router
for every preset, before the handler runs (`team_ids` is the repeated query parameter):
- no team → requires `can_observe_platform` on the org.
- teams given → a platform observer (`can_observe_platform`) may read any set of
  non-personal teams; anyone else needs `can_read_members` on every listed team (same
  permission the task bus's `scope=team` Activités view requires). A personal space
  always takes the member check. At most 200 teams (400 above).

There is no admin-only preset: observers read every preset, including storage and web
research. The router rejects `team_ids` with 400 for any preset whose
`team_scopable` is `False` — it never silently ignores it. **Never re-implement this
check inside a preset handler** — that is exactly the duplicated-authorization pattern
this module replaced (10 copies of the same three lines, pre-OBSERV-02-v3).

**Setting `team_scopable=True` is not just a signature change.** Verify the underlying
KPI event actually carries `dims.team_id` (grep its emission call site) before flipping
the flag — several presets in this package are deliberately `team_scopable=False`
because their source event has no team dimension or because
team-scoping them needs new store-layer work, not just a query filter. A preset silently returning unfiltered/wrong data for
team ids it doesn't actually honor is worse than not supporting team scoping at all.

## Adding a preset

1. Create `presets/my_preset.py`. Define a Pydantic response model and a handler
   function. Use `TimeSeriesResponse` from `common.py` for time-bucketed data, or
   define a custom model if the shape doesn't fit.

2. Use `resolve_interval(since, until)` from `utils.py` to get the right OpenSearch
   bucket interval and `strftime` format for the time range.

3. Register in `presets/__init__.py`:

```python
from control_plane_backend.kpi.presets.my_preset import MY_PRESET

PRESETS: list[PresetDef] = [
    ACTIVE_USERS_OVER_TIME_PRESET,
    MY_PRESET,               # add here
]
```

4. Regenerate the frontend types: `cd apps/frontend && make update-control-plane-api`

## Common response types

**`TimeSeriesResponse`** (`common.py`) — use for any time-bucketed metric:

```python
TimeSeriesResponse(
    rows=[TimeSeriesPoint(date="2026-06-12", value=42.0), …],
    since=since,   # AwareDatetime, passed through from the handler
    until=until,
    interval="1d", # the OpenSearch fixed_interval used
)
```

The frontend `TimeSeriesLineChart` molecule consumes this shape directly.

**`ScalarResponse`** (`common.py`) — use for any single integer metric over a time range:

```python
ScalarResponse(
    value=42,
    since=since,   # AwareDatetime, passed through from the handler
    until=until,
)
```

The frontend `KpiStatCard` molecule consumes this shape directly.

**Analytics section presets** (`analytics_*.py`) answer one tab section each,
for the period and the previous one of the same length: build the body with
`analytics_common.two_period_body(windows, team_ids, metrics, aggs)` (one search,
a `filters` agg splits the periods) and read it with `per_period` /
`PeriodValue`. Bodies with several 10 000-term aggs use `search_by_period`
instead (one search per period, below `search.max_buckets`). Over-time presets
set `bucketable=True` and use `utils.calendar_histogram` (calendar buckets in
`tz`, ISO bucket starts); counts and medians of per-entity counts live in
`distribution_utils.py`. Costs go through `analytics_common.token_aggs` /
`token_totals` (euros).
