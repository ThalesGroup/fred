# EcoAdvisor - Mobility & CO2 demo

EcoAdvisor is the Academy showcase that walks a Fred agent through low-carbon commute ideas around Lyon. The flow is intentionally lean: LangGraph (`reasoner ↔ tools`) plus two local MCP micro-services so the agent can cite real datasets instead of inventing numbers.

## TL;DR demo flow
1. Import the demo CSVs from `data/` into the Knowledge Flow tabular server: `bike_infra_demo`, `tcl_stops_demo`, plus `co2_emission_factors` (seeded from `data/Base_Carbone_V23.6.csv` or your trimmed ADEME export). The UI now owns CO₂ factors, no extra MCP service required.
2. Launch everything with `./start.sh`. The script boots Agentic Backend, Knowledge Flow, the front-end, and the two FastAPI MCP services (geo + TCL).
3. In the Agentic UI, go to **Tools → MCP servers → Add server** and register the remaining local services (configs no longer autoload them):
   | Alias in UI | URL |
   | --- | --- |
   | `mcp-geo-service` | `http://localhost:9801/mcp` |
   | `mcp-tcl-service` | `http://localhost:9802/mcp` |
4. Pick the **EcoAdvisor** agent, point it at a commute scenario, and let it call the MCP tools plus the tabular datasets. The agent responds with a Markdown brief (comparison table + CO₂ totals + assumptions).

## Repo tour
| Path | Purpose |
| --- | --- |
| `eco_adviser.py` | LangGraph agent + tuning metadata. |
| `geo_distance_service/` | FastAPI MCP for Nominatim/OSRM distance estimates with a haversine fallback. |
| `tcl_transit_service/` | FastAPI MCP for SYTRAL/TCL stops, with CSV fallback for offline demos. |
| `data/` | Curated CSVs (bike infra, TCL stops, ADEME CO₂ factors, etc.) ready to import via the UI. |

Old side documents (`TECH_DOC.md`, `ROADMAP.md`, …) were merged into this single README so every required instruction lives here.

## Demo datasets
- `data/bike_infra_demo.csv` – curated slice of the Lyon cycling infrastructure feed.
- `data/tcl_stops_demo.csv` – readable subset of TCL stops.
- `data/Base_Carbone_V23.6.csv` – ADEME emission factors: import it (or a trimmed version) as the `co2_emission_factors` table inside Knowledge Flow so EcoAdvisor can query it like any other dataset.

Need more context (energy mix, historic traffic, etc.)? Pull it from https://data.grandlyon.com or https://transport.data.gouv.fr directly—the repo purposely stays light.

## Local MCP services
| Service | Port | Key tools | Notes |
| --- | --- | --- | --- |
| `geo_distance_service` | `9801` | `geocode_location`, `compute_trip_distance`, `estimate_trip_between_addresses` | Wraps Nominatim + OSRM; falls back to simple haversine math offline. |
| `tcl_transit_service` | `9802` | `search_tcl_stops`, `find_nearby_tcl_stops`, `list_tcl_lines`, `get_tcl_metadata`, `reload_tcl_stops_cache` | Pulls SYTRAL/TCL WFS with a CSV fallback (`data/tcl_stops_demo.csv`). |

CO₂ computation is now fully tabular: load the emission CSV into Knowledge Flow and EcoAdvisor will query it through `mcp-knowledge-flow-mcp-tabular`. Because the UI owns MCP registration, `config/configuration*.yaml` only contains global defaults (no ECO-specific entries). If you run another instance, repeat the UI step above.

## How the agent reasons
- Minimal LangGraph state (`messages`, `database_context`).
- Loop pattern: `reasoner → tools → reasoner` until `tools_condition` says no more calls.
- System prompt automatically lists the DuckDB tables returned by the tabular MCP `get_context` call.
- Output: Markdown recap with a comparison table, total weekly CO₂, explicit assumptions, and tangible equivalents (vacuum hours, heating days, …).

## Ops tips
- Refresh emission factors by re-importing the CSV in Knowledge Flow (no env vars required now that CO₂ data is tabular).
- The TCL service honors `TCL_WFS_BASE_URL`, `TCL_WFS_TYPENAME`, `TCL_WFS_SRSNAME`, `TCL_WFS_PAGE_SIZE`, `TCL_WFS_MAX_FEATURES`, `TCL_STOPS_CACHE_TTL_SEC`, plus optional `TCL_WFS_USERNAME` / `TCL_WFS_PASSWORD` for authenticated feeds; it auto-falls back to the demo CSV otherwise.
- Keep `MAX_TOOL_MESSAGE_CHARS` and `ECO_RECENT_MESSAGES` tuned so tool payloads stay under your model limits.
- When you add a new MCP endpoint, expose it through FastAPI, start it in `start.sh`, and register it from the UI like the existing set.
