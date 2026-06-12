# KPI presets

Each KPI preset is a self-contained query that runs against OpenSearch and returns
structured data. Presets are auto-registered as GET endpoints under `/kpi/presets/<name>`.

## How it works

```
api.py          — iterates PRESETS, mounts one route per preset
presets/
  __init__.py   — PRESETS list (add your preset here)
  base.py       — PresetDef dataclass
  common.py     — shared response types (TimeSeriesResponse, …)
  <name>.py     — one file per preset
utils.py        — resolve_interval(): picks OpenSearch bucket size from time range
```

Every preset is a `PresetDef`:

```python
PresetDef(
    name="my_preset",          # becomes GET /kpi/presets/my_preset
    response_model=MyResponse, # Pydantic model — drives OpenAPI schema
    handler=query_my_preset,   # called with (store, user=…, since=…, until=…)
    summary="One-line description for OpenAPI docs",
)
```

The handler receives:
- `store: OpenSearchKPIStore` — call `store.client.search(index=store.index, body=…)`
- `user: KeycloakUser` — call `require_admin(user)` if admin-only
- `since / until: datetime` — the requested time range (UTC, always set)

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
